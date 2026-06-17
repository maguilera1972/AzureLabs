import logging

import httpx

from app.azure.auth import VM_SIZES
from app.azure.exchange_rate import eur_to_chf, get_eur_to_chf_rate
from app.azure.vm_utils import total_vm_count
from app.schemas import CostEstimateRequest, CostEstimateResponse, CostLineItem, ExchangeRateResponse

logger = logging.getLogger(__name__)

PRICES_API = "https://prices.azure.com/api/retail/prices"

FALLBACK_PRICES = {
    "Standard_D2s_v3": 0.096,
    "Standard_D4s_v3": 0.192,
    "Standard_D8s_v3": 0.384,
    "Standard_D16s_v3": 0.768,
    "Standard_D2s_v5": 0.10,
    "Standard_D4s_v5": 0.20,
    "Standard_D8s_v5": 0.40,
    "premium_ssd_p10": 0.025,
    "public_ip_standard": 0.005,
}

OS_LABELS = {
    "windows11": "Windows 11",
    "windowsserver2025": "Windows Server 2025",
    "ubuntu": "Ubuntu LTS",
}


async def _fetch_vm_price(vm_size: str, location: str) -> float:
    region = location.replace(" ", "").lower()
    filter_query = (
        f"serviceName eq 'Virtual Machines' "
        f"and armSkuName eq '{vm_size}' "
        f"and priceType eq 'Consumption' "
        f"and contains(armRegionName, '{region}')"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(PRICES_API, params={"$filter": filter_query})
            data = resp.json()
            items = data.get("Items", [])
            linux_prices = [
                i["unitPrice"] for i in items
                if "Windows" not in i.get("productName", "")
                and i.get("unitOfMeasure") == "1 Hour"
            ]
            if linux_prices:
                return min(linux_prices)
            windows_prices = [
                i["unitPrice"] for i in items
                if i.get("unitOfMeasure") == "1 Hour"
            ]
            if windows_prices:
                return min(windows_prices)
    except Exception as e:
        logger.warning("Retail Prices API error: %s", e)
    return FALLBACK_PRICES.get(vm_size, 0.192)


def _hours_per_day(start: int, stop: int) -> float:
    if stop > start:
        return float(stop - start)
    return float(24 - start + stop)


async def estimate_workshop_cost(request: CostEstimateRequest) -> CostEstimateResponse:
    rate = await get_eur_to_chf_rate()
    hours = _hours_per_day(request.schedule_start_hour, request.schedule_stop_hour)
    days = request.duration_days
    items: list[CostLineItem] = []

    for cfg in request.vms:
        qty = max(1, min(cfg.quantity, 100))
        size = cfg.vm_size or "Standard_D4s_v3"
        hourly_eur = await _fetch_vm_price(size, request.location)
        os_label = OS_LABELS.get(cfg.os_type, cfg.os_type)

        if cfg.os_type in ("windows11", "windowsserver2025"):
            hourly_eur *= 1.4

        vm_hours = hours * days * qty
        vm_cost_eur = hourly_eur * vm_hours
        prefix = cfg.name_prefix or "vm"
        items.append(CostLineItem(
            resource=f"{qty}× {os_label} — {prefix} ({size})",
            unit="heure",
            quantity=round(vm_hours, 1),
            unit_price_eur=round(hourly_eur, 4),
            monthly_cost_eur=round(vm_cost_eur, 2),
            unit_price_chf=eur_to_chf(hourly_eur, rate.eur_to_chf, 4),
            monthly_cost_chf=eur_to_chf(vm_cost_eur, rate.eur_to_chf),
        ))

        disk_hourly = FALLBACK_PRICES["premium_ssd_p10"]
        disk_hours = hours * days * qty
        disk_cost_eur = disk_hourly * disk_hours
        items.append(CostLineItem(
            resource=f"{qty}× Disque Premium 128 Go — {prefix}",
            unit="heure",
            quantity=round(disk_hours, 1),
            unit_price_eur=disk_hourly,
            monthly_cost_eur=round(disk_cost_eur, 2),
            unit_price_chf=eur_to_chf(disk_hourly, rate.eur_to_chf, 4),
            monthly_cost_chf=eur_to_chf(disk_cost_eur, rate.eur_to_chf),
        ))

        ip_hourly = FALLBACK_PRICES["public_ip_standard"]
        ip_hours = hours * days * qty
        ip_cost_eur = ip_hourly * ip_hours
        items.append(CostLineItem(
            resource=f"{qty}× IP publique — {prefix}",
            unit="heure",
            quantity=round(ip_hours, 1),
            unit_price_eur=ip_hourly,
            monthly_cost_eur=round(ip_cost_eur, 2),
            unit_price_chf=eur_to_chf(ip_hourly, rate.eur_to_chf, 4),
            monthly_cost_chf=eur_to_chf(ip_cost_eur, rate.eur_to_chf),
        ))

    total_workshop_eur = sum(i.monthly_cost_eur for i in items)
    total_daily_eur = total_workshop_eur / days if days else 0

    return CostEstimateResponse(
        total_workshop_eur=round(total_workshop_eur, 2),
        total_workshop_chf=eur_to_chf(total_workshop_eur, rate.eur_to_chf),
        total_daily_eur=round(total_daily_eur, 2),
        total_daily_chf=eur_to_chf(total_daily_eur, rate.eur_to_chf),
        hours_per_day=hours,
        duration_days=days,
        total_vm_count=total_vm_count(request.vms),
        items=items,
        exchange_rate=ExchangeRateResponse(
            eur_to_chf=rate.eur_to_chf,
            chf_to_eur=rate.chf_to_eur,
            updated_at=rate.updated_at,
            source=rate.source,
        ),
    )


def compute_hardware_totals(vms: list[dict]) -> dict:
    total_vcpu = 0
    total_ram = 0
    running = 0
    stopped = 0
    for vm in vms:
        size = vm.get("vm_size", "Standard_D4s_v3")
        spec = VM_SIZES.get(size, {"vcpu": 4, "ram_gb": 16})
        total_vcpu += spec["vcpu"]
        total_ram += spec["ram_gb"]
        state = vm.get("power_state", "unknown").lower()
        if state == "running":
            running += 1
        elif state in ("deallocated", "stopped", "poweredoff"):
            stopped += 1
    return {
        "total_vcpu": total_vcpu,
        "total_ram_gb": total_ram,
        "running_vms": running,
        "stopped_vms": stopped,
    }
