from __future__ import annotations

from celery import shared_task

from . import services


@shared_task
def refresh_investments() -> dict[str, int]:
    """Daily: gold (NBP) and crypto (CoinGecko) prices, GUS inflation for bonds."""
    return services.refresh_all()
