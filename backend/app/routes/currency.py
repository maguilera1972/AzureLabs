from fastapi import APIRouter, Depends

from app.azure.exchange_rate import get_eur_to_chf_rate
from app.models import ConsoleUser
from app.schemas import ExchangeRateResponse
from app.services.console_auth import get_current_user

router = APIRouter(prefix="/api/currency", tags=["currency"])


@router.get("/rate", response_model=ExchangeRateResponse)
async def get_exchange_rate(_: ConsoleUser = Depends(get_current_user)):
    rate = await get_eur_to_chf_rate()
    return ExchangeRateResponse(
        eur_to_chf=rate.eur_to_chf,
        chf_to_eur=rate.chf_to_eur,
        updated_at=rate.updated_at,
        source=rate.source,
    )
