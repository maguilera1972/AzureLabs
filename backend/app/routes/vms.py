import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.azure.vm_provisioner import get_vm_power_state, start_vm, stop_vm
from app.database import get_db
from app.models import ConsoleUser, VirtualMachine, Workshop
from app.services.console_auth import get_current_user
from app.services.credentials import get_active_credentials

router = APIRouter(prefix="/api/vms", tags=["vms"])


@router.post("/{workshop_id}/{vm_name}/start")
async def vm_start(
    workshop_id: int,
    vm_name: str,
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

    await asyncio.to_thread(start_vm, creds, workshop.resource_group, vm_name)

    vm_result = await db.execute(
        select(VirtualMachine).where(
            VirtualMachine.workshop_id == workshop_id,
            VirtualMachine.name == vm_name,
        )
    )
    vm = vm_result.scalar_one_or_none()
    if vm:
        vm.power_state = "running"
        await db.commit()

    return {"status": "started", "vm": vm_name}


@router.post("/{workshop_id}/{vm_name}/stop")
async def vm_stop(
    workshop_id: int,
    vm_name: str,
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

    await asyncio.to_thread(stop_vm, creds, workshop.resource_group, vm_name)

    vm_result = await db.execute(
        select(VirtualMachine).where(
            VirtualMachine.workshop_id == workshop_id,
            VirtualMachine.name == vm_name,
        )
    )
    vm = vm_result.scalar_one_or_none()
    if vm:
        vm.power_state = "deallocated"
        await db.commit()

    return {"status": "stopped", "vm": vm_name}


@router.get("/{workshop_id}/{vm_name}/status")
async def vm_status(
    workshop_id: int,
    vm_name: str,
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

    state = await asyncio.to_thread(
        get_vm_power_state, creds, workshop.resource_group, vm_name
    )
    return {"vm": vm_name, "power_state": state}
