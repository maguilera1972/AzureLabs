from datetime import date, datetime, timedelta

from app.azure.exchange_rate import eur_to_chf
from app.models import Workshop

ACTIVE_STATUSES = {"ready", "creating", "deleting"}


def _workshop_daily_cost_eur(workshop: Workshop) -> float:
    days = max(workshop.duration_days, 1)
    if workshop.estimated_monthly_cost_eur <= 0:
        return 0.0
    return workshop.estimated_monthly_cost_eur / days


def _workshop_period(workshop: Workshop) -> tuple[date, date]:
    created = workshop.created_at.date() if workshop.created_at else date.today()
    end = created + timedelta(days=max(workshop.duration_days, 1) - 1)
    return created, end


def _is_active_workshop(workshop: Workshop) -> bool:
    status = (workshop.status or "").lower()
    if status.startswith("error"):
        return False
    return status in ACTIVE_STATUSES or status == ""


def build_consumption_timeline(
    workshops: list[Workshop],
    eur_to_chf_rate: float,
    *,
    days_back: int = 30,
    days_forward: int = 14,
) -> dict:
    today = datetime.utcnow().date()
    active_workshops = [w for w in workshops if _is_active_workshop(w)]

    if active_workshops:
        earliest = min(_workshop_period(w)[0] for w in active_workshops)
        latest = max(_workshop_period(w)[1] for w in active_workshops)
        start = min(earliest, today - timedelta(days=days_back))
        end = max(latest, today + timedelta(days=days_forward))
    else:
        start = today - timedelta(days=days_back)
        end = today + timedelta(days=min(days_forward, 7))

    if (end - start).days > 120:
        end = start + timedelta(days=120)

    points: list[dict] = []
    cumulative_eur = 0.0
    peak_daily_eur = 0.0
    peak_daily_chf = 0.0
    peak_date: str | None = None

    current = start
    while current <= end:
        day_workshops: list[dict] = []
        daily_eur = 0.0

        for workshop in active_workshops:
            period_start, period_end = _workshop_period(workshop)
            if period_start <= current <= period_end:
                unit = _workshop_daily_cost_eur(workshop)
                daily_eur += unit
                day_workshops.append({
                    "workshop_id": workshop.id,
                    "workshop_name": workshop.name,
                    "daily_cost_eur": round(unit, 2),
                    "daily_cost_chf": eur_to_chf(unit, eur_to_chf_rate),
                })

        daily_eur = round(daily_eur, 2)
        daily_chf = eur_to_chf(daily_eur, eur_to_chf_rate)
        cumulative_eur = round(cumulative_eur + daily_eur, 2)
        cumulative_chf = eur_to_chf(cumulative_eur, eur_to_chf_rate)

        if daily_eur > peak_daily_eur:
            peak_daily_eur = daily_eur
            peak_daily_chf = daily_chf
            peak_date = current.isoformat()

        points.append({
            "date": current.isoformat(),
            "daily_cost_eur": daily_eur,
            "daily_cost_chf": daily_chf,
            "cumulative_cost_eur": cumulative_eur,
            "cumulative_cost_chf": cumulative_chf,
            "active_workshop_count": len(day_workshops),
            "workshops": day_workshops,
            "is_today": current == today,
            "is_future": current > today,
        })
        current += timedelta(days=1)

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "today": today.isoformat(),
        "days": points,
        "peak_daily_cost_eur": round(peak_daily_eur, 2),
        "peak_daily_cost_chf": round(peak_daily_chf, 2),
        "peak_date": peak_date,
        "active_workshop_count": len(active_workshops),
    }
