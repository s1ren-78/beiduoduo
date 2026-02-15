"""Financial statement sync logic (SEC EDGAR + Artemis protocol financials)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any

from .config import Settings
from .db import DB
from .db_market import get_watchlist, upsert_fin_statement
from .market_api import ArtemisClient
from .sec_api import SECEdgarClient

logger = logging.getLogger(__name__)


@dataclass
class FinSyncStats:
    stocks_synced: int = 0
    protocols_synced: int = 0
    rows_written: int = 0
    failures: list[str] = field(default_factory=list)

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def sync_financials(
    db: DB,
    settings: Settings,
    *,
    mode: str = "full",
    run_id: str | None = None,
) -> FinSyncStats:
    stats = FinSyncStats()

    # ── SEC EDGAR (stocks) ──
    if settings.sec_edgar_user_agent:
        sec = SECEdgarClient(settings.sec_edgar_user_agent)
        for item in get_watchlist(db, asset_class="stock"):
            ticker = item["symbol"]
            try:
                rows = sec.get_financials(ticker)
                count = upsert_fin_statement(db, rows)
                stats.rows_written += count
                stats.stocks_synced += 1
            except Exception as e:
                logger.error("SEC financials sync failed for %s: %s", ticker, e)
                stats.failures.append(f"sec:{ticker}:{e}")

    # ── Artemis protocol financials ──
    if settings.artemis_api_key:
        artemis = ArtemisClient(settings.artemis_api_key)
        for item in get_watchlist(db, asset_class="protocol"):
            protocol = item["symbol"]
            try:
                rows = artemis.get_protocol_financials(protocol)
                count = upsert_fin_statement(db, rows)
                stats.rows_written += count
                stats.protocols_synced += 1
            except Exception as e:
                logger.error("Protocol financials sync failed for %s: %s", protocol, e)
                stats.failures.append(f"protocol:{protocol}:{e}")

    return stats
