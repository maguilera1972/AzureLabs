import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

FALLBACK_EUR_TO_CHF = 0.921
CACHE_TTL_SECONDS = 3600

RATE_SOURCES = [
    {
        "name": "exchangerate-api.com",
        "url": "https://api.exchangerate-api.com/v4/latest/EUR",
        "parse": lambda d: (d["rates"]["CHF"], d.get("date", "")),
    },
    {
        "name": "open.er-api.com",
        "url": "https://open.er-api.com/v6/latest/EUR",
        "parse": lambda d: (d["rates"]["CHF"], d.get("time_last_update_utc", "")[:10]),
    },
    {
        "name": "frankfurter.app (BCE)",
        "url": "https://api.frankfurter.app/latest",
        "params": {"from": "EUR", "to": "CHF"},
        "parse": lambda d: (d["rates"]["CHF"], d.get("date", "")),
    },
]


@dataclass
class ExchangeRate:
    eur_to_chf: float
    chf_to_eur: float
    updated_at: str
    source: str


_cache: ExchangeRate | None = None
_cache_time: float = 0.0


async def get_eur_to_chf_rate() -> ExchangeRate:
    global _cache, _cache_time

    if _cache and (time.time() - _cache_time) < CACHE_TTL_SECONDS:
        return _cache

    async with httpx.AsyncClient(timeout=10) as client:
        for source in RATE_SOURCES:
            try:
                params = source.get("params")
                resp = await client.get(source["url"], params=params)
                resp.raise_for_status()
                data = resp.json()
                rate, updated = source["parse"](data)
                _cache = ExchangeRate(
                    eur_to_chf=round(float(rate), 6),
                    chf_to_eur=round(1 / float(rate), 6),
                    updated_at=updated or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    source=source["name"],
                )
                _cache_time = time.time()
                logger.info("Exchange rate EUR→CHF: %s (source: %s)", rate, source["name"])
                return _cache
            except Exception as e:
                logger.warning("Rate source %s failed: %s", source["name"], e)

    logger.warning("All exchange rate sources failed, using fallback")
    if _cache:
        return _cache
    return ExchangeRate(
        eur_to_chf=FALLBACK_EUR_TO_CHF,
        chf_to_eur=round(1 / FALLBACK_EUR_TO_CHF, 6),
        updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        source="fallback",
    )


def eur_to_chf(amount_eur: float, rate: float, decimals: int = 2) -> float:
    return round(amount_eur * rate, decimals)
