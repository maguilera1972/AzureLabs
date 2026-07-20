import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.azure.auth import OS_IMAGES, resource_group_name, slugify
from app.azure.automation import setup_workshop_schedules
from app.azure.cost_estimator import estimate_workshop_cost
from app.azure.exchange_rate import eur_to_chf, get_eur_to_chf_rate
from app.azure.pdf_export import generate_workshop_credentials_pdf
from app.azure.quote_pdf import generate_cost_quote_pdf
from app.azure.vm_utils import expand_vm_configs
from app.azure.vm_provisioner import (
    create_resource_group,
    delete_resource_group,
    list_vms_in_group,
    provision_vm,
    resource_group_exists,
)
from app.config import settings
from app.crypto import decrypt_secret, encrypt_secret
from app.database import get_db
from app.models import ConsoleUser, VirtualMachine, Workshop
from app.schemas import (
    CostEstimateRequest,
    CostEstimateResponse,
    ConsumptionTimeline,
    ExchangeRateResponse,
    SubscriptionMetrics,
    QuotePdfRequest,
    VMDefinition,
    VMResponse,
    VMCredentialsResponse,
    WorkshopCreateRequest,
    WorkshopMetrics,
    WorkshopResponse,
)
from app.services.console_auth import get_current_user, user_display_name
from app.services.consumption_timeline import build_consumption_timeline

from app.services.credentials import get_active_credentials, get_active_connection_record

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workshops", tags=["workshops"])


async def _load_creators_map(db: AsyncSession, workshops: list[Workshop]) -> dict[int, ConsoleUser]:
    ids = {w.created_by_user_id for w in workshops if w.created_by_user_id}
    if not ids:
        return {}
    result = await db.execute(select(ConsoleUser).where(ConsoleUser.id.in_(ids)))
    return {u.id: u for u in result.scalars().all()}


def _workshop_to_response(
    w: Workshop,
    eur_chf_rate: float,
    creator: ConsoleUser | None = None,
) -> WorkshopResponse:
    return WorkshopResponse(
        id=w.id,
        name=w.name,
        slug=w.slug,
        resource_group=w.resource_group,
        location=w.location,
        subscription_id=w.subscription_id,
        vm_count=w.vm_count,
        schedule_start_hour=w.schedule_start_hour,
        schedule_stop_hour=w.schedule_stop_hour,
        schedule_timezone=w.schedule_timezone,
        schedule_enabled=w.schedule_enabled,
        duration_days=getattr(w, "duration_days", 5) or 5,
        status=w.status,
        estimated_monthly_cost_eur=w.estimated_monthly_cost_eur,
        estimated_monthly_cost_chf=eur_to_chf(w.estimated_monthly_cost_eur, eur_chf_rate),
        created_at=w.created_at.isoformat(),
        created_by_user_id=w.created_by_user_id,
        created_by_username=creator.username if creator else None,
        created_by_display_name=user_display_name(creator) if creator else None,
        created_by_email=creator.email if creator else None,
    )


def _pending_vm_record(workshop_id: int, vm_def: VMDefinition) -> VirtualMachine:
    image = OS_IMAGES[vm_def.os_type]
    return VirtualMachine(
        workshop_id=workshop_id,
        name=vm_def.name,
        os_type=vm_def.os_type,
        vm_size=vm_def.vm_size or settings.default_vm_size,
        admin_username=vm_def.admin_username,
        admin_password_encrypted=encrypt_secret(vm_def.admin_password),
        remote_protocol=image["remote_protocol"],
        remote_port=image["remote_port"],
        status="pending",
    )


async def _load_workshop_vms(db: AsyncSession, workshop_id: int) -> list[VirtualMachine]:
    result = await db.execute(
        select(VirtualMachine)
        .where(VirtualMachine.workshop_id == workshop_id)
        .order_by(VirtualMachine.name)
    )
    return list(result.scalars().all())


async def _finalize_workshop_deletion(db: AsyncSession, workshop_id: int) -> bool:
    result = await db.execute(select(Workshop).where(Workshop.id == workshop_id))
    workshop = result.scalar_one_or_none()
    if not workshop:
        return False

    vm_result = await db.execute(
        select(VirtualMachine).where(VirtualMachine.workshop_id == workshop_id)
    )
    for vm in vm_result.scalars().all():
        await db.delete(vm)
    await db.delete(workshop)
    await db.commit()
    return True


async def _sync_deleting_workshop(db: AsyncSession, workshop: Workshop) -> bool:
    """Finalize local deletion when Azure resource group is already gone."""
    if workshop.status != "deleting":
        return False

    creds = await get_active_credentials(db)
    if not creds:
        return False

    try:
        exists = await asyncio.to_thread(
            resource_group_exists, creds, workshop.resource_group
        )
    except Exception:
        logger.exception("Failed to check Azure RG %s", workshop.resource_group)
        return False

    if exists:
        return False

    logger.info("Azure RG %s gone — finalizing workshop %s deletion", workshop.resource_group, workshop.id)
    return await _finalize_workshop_deletion(db, workshop.id)


async def _provision_workshop(workshop_id: int, req: WorkshopCreateRequest, creds_data: dict):
    from app.azure.auth import AzureCredentials
    from app.database import async_session

    creds = AzureCredentials(**creds_data)

    async with async_session() as db:
        result = await db.execute(select(Workshop).where(Workshop.id == workshop_id))
        workshop = result.scalar_one_or_none()
        if not workshop:
            return

        location = req.location or "francecentral"
        rg = workshop.resource_group

        try:
            create_resource_group(creds, rg, location)

            vm_records = await _load_workshop_vms(db, workshop_id)
            if not vm_records:
                expanded_vms = expand_vm_configs(req.vms)
                for vm_def in expanded_vms:
                    db.add(_pending_vm_record(workshop_id, vm_def))
                await db.commit()
                vm_records = await _load_workshop_vms(db, workshop_id)

            for vm_record in vm_records:
                vm_record.status = "provisioning"
                await db.commit()

                password = decrypt_secret(vm_record.admin_password_encrypted)
                vm_result = await asyncio.to_thread(
                    provision_vm,
                    creds, rg, location,
                    vm_record.name, vm_record.os_type,
                    vm_record.admin_username, password,
                    vm_record.vm_size,
                )
                vm_record.os_type = vm_result["os_type"]
                vm_record.vm_size = vm_result["vm_size"]
                vm_record.admin_username = vm_result["admin_username"]
                vm_record.public_ip = vm_result["public_ip"]
                vm_record.private_ip = vm_result["private_ip"]
                vm_record.remote_protocol = vm_result["remote_protocol"]
                vm_record.remote_port = vm_result["remote_port"]
                vm_record.power_state = vm_result["power_state"]
                vm_record.azure_vm_id = vm_result["azure_vm_id"]
                vm_record.status = "ready"
                await db.commit()

            if req.schedule_enabled:
                await asyncio.to_thread(
                    setup_workshop_schedules,
                    creds, rg, location,
                    req.schedule_start_hour, req.schedule_stop_hour,
                    req.schedule_timezone,
                )

            cost = await estimate_workshop_cost(CostEstimateRequest(
                location=location,
                vms=req.vms,
                schedule_start_hour=req.schedule_start_hour,
                schedule_stop_hour=req.schedule_stop_hour,
                duration_days=req.duration_days,
            ))

            workshop.status = "ready"
            workshop.vm_count = len(vm_records)
            workshop.estimated_monthly_cost_eur = cost.total_workshop_eur
            await db.commit()

        except Exception as e:
            logger.exception("Workshop provisioning failed: %s", e)
            workshop.status = f"error: {str(e)[:200]}"
            await db.commit()


@router.get("", response_model=list[WorkshopResponse])
async def list_workshops(
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    rate = await get_eur_to_chf_rate()
    result = await db.execute(select(Workshop).order_by(Workshop.created_at.desc()))
    workshops = list(result.scalars().all())

    visible = []
    for workshop in workshops:
        if workshop.status == "deleting" and await _sync_deleting_workshop(db, workshop):
            continue
        visible.append(workshop)

    creators = await _load_creators_map(db, visible)
    return [
        _workshop_to_response(w, rate.eur_to_chf, creators.get(w.created_by_user_id))
        for w in visible
    ]


@router.post("", response_model=WorkshopResponse)
async def create_workshop(
    req: WorkshopCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: ConsoleUser = Depends(get_current_user),
):
    creds = await get_active_credentials(db)
    if not creds:
        raise HTTPException(400, "Connectez-vous d'abord à Azure")

    conn = await get_active_connection_record(db)
    slug = slugify(req.name)
    rg = resource_group_name(req.name)

    existing = await db.execute(select(Workshop).where(Workshop.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Un atelier '{req.name}' existe déjà")

    cost = await estimate_workshop_cost(CostEstimateRequest(
        location=req.location or "francecentral",
        vms=req.vms,
        schedule_start_hour=req.schedule_start_hour,
        schedule_stop_hour=req.schedule_stop_hour,
        duration_days=req.duration_days,
    ))

    expanded_vms = expand_vm_configs(req.vms)

    workshop = Workshop(
        name=req.name,
        slug=slug,
        resource_group=rg,
        location=req.location or "francecentral",
        subscription_id=creds.subscription_id,
        vm_count=len(expanded_vms),
        schedule_start_hour=req.schedule_start_hour,
        schedule_stop_hour=req.schedule_stop_hour,
        schedule_timezone=req.schedule_timezone,
        schedule_enabled=req.schedule_enabled,
        duration_days=req.duration_days,
        status="creating",
        estimated_monthly_cost_eur=cost.total_workshop_eur,
        created_by_user_id=current_user.id,
    )
    db.add(workshop)
    await db.commit()
    await db.refresh(workshop)

    for vm_def in expanded_vms:
        db.add(_pending_vm_record(workshop.id, vm_def))
    await db.commit()

    background_tasks.add_task(
        _provision_workshop,
        workshop.id,
        req,
        {
            "tenant_id": creds.tenant_id,
            "username": creds.username,
            "subscription_id": creds.subscription_id,
            "auth_type": creds.auth_type,
            "password": creds.password,
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        },
    )

    rate = await get_eur_to_chf_rate()
    return _workshop_to_response(workshop, rate.eur_to_chf, current_user)


@router.get("/{workshop_id}", response_model=WorkshopResponse)
async def get_workshop(
    workshop_id: int,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    rate = await get_eur_to_chf_rate()
    result = await db.execute(select(Workshop).where(Workshop.id == workshop_id))
    workshop = result.scalar_one_or_none()
    if not workshop:
        raise HTTPException(404, "Atelier introuvable")

    if await _sync_deleting_workshop(db, workshop):
        raise HTTPException(404, "Atelier introuvable")

    creator = None
    if workshop.created_by_user_id:
        result = await db.execute(
            select(ConsoleUser).where(ConsoleUser.id == workshop.created_by_user_id)
        )
        creator = result.scalar_one_or_none()

    return _workshop_to_response(workshop, rate.eur_to_chf, creator)


@router.get("/{workshop_id}/vms", response_model=list[VMResponse])
async def get_workshop_vms(
    workshop_id: int,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    creds = await get_active_credentials(db)
    result = await db.execute(select(Workshop).where(Workshop.id == workshop_id))
    workshop = result.scalar_one_or_none()
    if not workshop:
        raise HTTPException(404, "Atelier introuvable")

    vm_result = await db.execute(
        select(VirtualMachine)
        .where(VirtualMachine.workshop_id == workshop_id)
        .order_by(VirtualMachine.name)
    )
    vms = vm_result.scalars().all()

    azure_by_name: dict[str, dict] = {}
    if creds and workshop.status in ("creating", "ready"):
        try:
            azure_vms = await asyncio.to_thread(
                list_vms_in_group, creds, workshop.resource_group
            )
            azure_by_name = {v["name"]: v for v in azure_vms}
            if workshop.status == "ready":
                updated = False
                for vm in vms:
                    if vm.name in azure_by_name:
                        power = azure_by_name[vm.name]["power_state"]
                        if power != "unknown" and vm.power_state != power:
                            vm.power_state = power
                            updated = True
                if updated:
                    await db.commit()
        except Exception:
            logger.exception("Azure VM sync failed for workshop %s", workshop_id)

    if vms:
        return [
            _vm_to_response(vm, azure_by_name.get(vm.name, {}))
            for vm in vms
        ]

    if azure_by_name:
        return [
            VMResponse(
                id=0,
                workshop_id=workshop_id,
                name=av["name"],
                os_type=av.get("os_type") or "unknown",
                vm_size=av.get("vm_size") or "",
                admin_username="—",
                public_ip="",
                private_ip="",
                remote_protocol="",
                remote_port=0,
                power_state=av.get("power_state") or "unknown",
                status="provisioning",
                provisioning_state=av.get("provisioning_state") or "",
            )
            for av in azure_by_name.values()
        ]

    return []


def _vm_to_response(vm: VirtualMachine, azure_vm: dict) -> VMResponse:
    provisioning_state = azure_vm.get("provisioning_state", "")
    power_state = vm.power_state
    if azure_vm.get("power_state") and azure_vm["power_state"] != "unknown":
        power_state = azure_vm["power_state"]
    password = ""
    if vm.admin_password_encrypted:
        try:
            password = decrypt_secret(vm.admin_password_encrypted)
        except Exception:
            password = ""
    return VMResponse(
        id=vm.id,
        workshop_id=vm.workshop_id,
        name=vm.name,
        os_type=vm.os_type,
        vm_size=vm.vm_size,
        admin_username=vm.admin_username,
        admin_password=password,
        public_ip=vm.public_ip,
        private_ip=vm.private_ip,
        remote_protocol=vm.remote_protocol,
        remote_port=vm.remote_port,
        power_state=power_state,
        status=vm.status,
        provisioning_state=provisioning_state,
    )


@router.get("/{workshop_id}/vms/{vm_id}/credentials", response_model=VMCredentialsResponse)
async def get_vm_credentials(
    workshop_id: int,
    vm_id: int,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    from app.crypto import decrypt_secret
    result = await db.execute(
        select(VirtualMachine).where(
            VirtualMachine.id == vm_id,
            VirtualMachine.workshop_id == workshop_id,
        )
    )
    vm = result.scalar_one_or_none()
    if not vm:
        raise HTTPException(404, "VM introuvable")
    return VMCredentialsResponse(
        name=vm.name,
        admin_username=vm.admin_username,
        admin_password=decrypt_secret(vm.admin_password_encrypted),
        public_ip=vm.public_ip,
        remote_protocol=vm.remote_protocol,
        remote_port=vm.remote_port,
    )


@router.get("/{workshop_id}/credentials.pdf")
async def download_credentials_pdf(
    workshop_id: int,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    from app.crypto import decrypt_secret

    result = await db.execute(select(Workshop).where(Workshop.id == workshop_id))
    workshop = result.scalar_one_or_none()
    if not workshop:
        raise HTTPException(404, "Atelier introuvable")

    vm_result = await db.execute(
        select(VirtualMachine).where(VirtualMachine.workshop_id == workshop_id).order_by(VirtualMachine.name)
    )
    vms = vm_result.scalars().all()
    if not vms:
        raise HTTPException(404, "Aucun identifiant généré pour cet atelier")

    vm_data = [
        {
            "name": vm.name,
            "os_type": vm.os_type,
            "vm_size": vm.vm_size,
            "public_ip": vm.public_ip,
            "private_ip": vm.private_ip,
            "remote_protocol": vm.remote_protocol,
            "remote_port": vm.remote_port,
            "admin_username": vm.admin_username,
            "admin_password": decrypt_secret(vm.admin_password_encrypted),
        }
        for vm in vms
    ]

    pdf_bytes = generate_workshop_credentials_pdf(
        workshop_name=workshop.name,
        resource_group=workshop.resource_group,
        location=workshop.location,
        duration_days=getattr(workshop, "duration_days", 5) or 5,
        vms=vm_data,
    )

    filename = f"identifiants-{workshop.slug}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{workshop_id}")
async def delete_workshop(
    workshop_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    creds = await get_active_credentials(db)
    if not creds:
        raise HTTPException(400, "Connectez-vous d'abord à Azure")

    result = await db.execute(select(Workshop).where(Workshop.id == workshop_id))
    workshop = result.scalar_one_or_none()
    if not workshop:
        raise HTTPException(404, "Atelier introuvable")

    workshop.status = "deleting"
    await db.commit()

    async def _delete():
        try:
            await asyncio.to_thread(delete_resource_group, creds, workshop.resource_group)
        except Exception as e:
            logger.error("Delete RG failed: %s", e)
        from app.database import async_session
        async with async_session() as session:
            await _finalize_workshop_deletion(session, workshop_id)

    background_tasks.add_task(_delete)
    return {"status": "deleting", "resource_group": workshop.resource_group}


@router.post("/estimate", response_model=CostEstimateResponse)
async def estimate_cost(
    req: CostEstimateRequest,
    _: ConsoleUser = Depends(get_current_user),
):
    return await estimate_workshop_cost(req)


@router.post("/estimate/quote.pdf")
async def download_quote_pdf(
    req: QuotePdfRequest,
    _: ConsoleUser = Depends(get_current_user),
):
    if req.cost_snapshot:
        cost = req.cost_snapshot
    else:
        cost = await estimate_workshop_cost(req)
    currency = req.currency.upper() if req.currency.upper() in ("CHF", "EUR") else "CHF"
    pdf_bytes = generate_cost_quote_pdf(
        workshop_name=req.workshop_name,
        client_name=req.client_name,
        location=req.location,
        schedule_start_hour=req.schedule_start_hour,
        schedule_stop_hour=req.schedule_stop_hour,
        vms=req.vms,
        cost=cost,
        currency=currency,
    )
    slug = slugify(req.workshop_name or "atelier-azure")
    filename = f"offre-{slug}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/metrics/subscription", response_model=SubscriptionMetrics)
async def subscription_metrics(
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    from app.azure.cost_estimator import compute_hardware_totals

    rate = await get_eur_to_chf_rate()
    conn = await get_active_connection_record(db)
    creds = await get_active_credentials(db)

    result = await db.execute(select(Workshop).order_by(Workshop.name))
    workshops = result.scalars().all()

    workshop_metrics = []
    total_vms = 0
    total_running = 0
    total_vcpu = 0
    total_ram = 0
    total_cost_eur = 0.0

    for w in workshops:
        vm_result = await db.execute(
            select(VirtualMachine).where(VirtualMachine.workshop_id == w.id)
        )
        vms = vm_result.scalars().all()
        vm_dicts = [{"vm_size": v.vm_size, "power_state": v.power_state} for v in vms]

        if creds and w.status == "ready":
            try:
                azure_vms = await asyncio.to_thread(
                    list_vms_in_group, creds, w.resource_group
                )
                for i, av in enumerate(azure_vms):
                    if i < len(vm_dicts):
                        vm_dicts[i]["power_state"] = av["power_state"]
            except Exception:
                pass

        hw = compute_hardware_totals(vm_dicts)
        wm = WorkshopMetrics(
            workshop_id=w.id,
            workshop_name=w.name,
            resource_group=w.resource_group,
            vm_count=len(vms),
            running_vms=hw["running_vms"],
            stopped_vms=hw["stopped_vms"],
            total_vcpu=hw["total_vcpu"],
            total_ram_gb=hw["total_ram_gb"],
            estimated_monthly_cost_eur=w.estimated_monthly_cost_eur,
            estimated_monthly_cost_chf=eur_to_chf(w.estimated_monthly_cost_eur, rate.eur_to_chf),
        )
        workshop_metrics.append(wm)
        total_vms += len(vms)
        total_running += hw["running_vms"]
        total_vcpu += hw["total_vcpu"]
        total_ram += hw["total_ram_gb"]
        total_cost_eur += w.estimated_monthly_cost_eur

    timeline_data = build_consumption_timeline(workshops, rate.eur_to_chf)

    return SubscriptionMetrics(
        subscription_id=conn.subscription_id if conn else "",
        subscription_name=conn.subscription_name if conn else "Non connecté",
        workshop_count=len(workshops),
        total_vms=total_vms,
        running_vms=total_running,
        total_vcpu=total_vcpu,
        total_ram_gb=total_ram,
        estimated_monthly_cost_eur=round(total_cost_eur, 2),
        estimated_monthly_cost_chf=eur_to_chf(total_cost_eur, rate.eur_to_chf),
        exchange_rate=ExchangeRateResponse(
            eur_to_chf=rate.eur_to_chf,
            chf_to_eur=rate.chf_to_eur,
            updated_at=rate.updated_at,
            source=rate.source,
        ),
        workshops=workshop_metrics,
        consumption_timeline=ConsumptionTimeline(**timeline_data),
    )
