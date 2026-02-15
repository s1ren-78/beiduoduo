"""Market and on-chain data sync logic."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any

from .config import Settings
from .db import DB
from .db_market import (
    get_watchlist,
    upsert_price_daily,
    upsert_quote_latest,
    upsert_protocol_daily,
    upsert_chain_daily,
    upsert_token_liquidity,
)
from .market_api import ArtemisClient, YFinanceClient

logger = logging.getLogger(__name__)


@dataclass
class MarketSyncStats:
    stocks_synced: int = 0
    crypto_synced: int = 0
    protocols_synced: int = 0
    chains_synced: int = 0
    liquidity_synced: int = 0
    price_rows: int = 0
    quotes_updated: int = 0
    failures: list[str] = field(default_factory=list)

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def sync_market(
    db: DB,
    settings: Settings,
    *,
    mode: str = "full",
    run_id: str | None = None,
) -> MarketSyncStats:
    stats = MarketSyncStats()
    days = settings.market_history_days if mode == "full" else 2

    yf_client = YFinanceClient()
    artemis = ArtemisClient(settings.artemis_api_key) if settings.artemis_api_key else None

    # ── Stocks ──
    for item in get_watchlist(db, asset_class="stock"):
        symbol = item["symbol"]
        try:
            rows = yf_client.get_history(symbol, days=days)
            count = upsert_price_daily(db, rows)
            stats.price_rows += count

            quote = yf_client.get_quote(symbol)
            if quote:
                upsert_quote_latest(
                    db, symbol, "stock",
                    quote["price"], quote["change_pct"],
                    quote["volume"], quote["market_cap"],
                    meta=quote.get("meta"),
                )
                stats.quotes_updated += 1
            stats.stocks_synced += 1
        except Exception as e:
            logger.error("Stock sync failed for %s: %s", symbol, e)
            stats.failures.append(f"stock:{symbol}:{e}")

    # ── Crypto ──
    if artemis:
        for item in get_watchlist(db, asset_class="crypto"):
            symbol = item["symbol"]
            try:
                rows = artemis.get_crypto_history(symbol, days=days)
                count = upsert_price_daily(db, rows)
                stats.price_rows += count

                quote = artemis.get_crypto_quote(symbol)
                if quote:
                    upsert_quote_latest(
                        db, symbol, "crypto",
                        quote["price"], quote["change_pct"],
                        quote["volume"], quote["market_cap"],
                    )
                    stats.quotes_updated += 1
                stats.crypto_synced += 1
            except Exception as e:
                logger.error("Crypto sync failed for %s: %s", symbol, e)
                stats.failures.append(f"crypto:{symbol}:{e}")

        # ── Protocols ──
        for item in get_watchlist(db, asset_class="protocol"):
            protocol = item["symbol"]
            try:
                rows = artemis.get_protocol_metrics(protocol, days=days)
                count = upsert_protocol_daily(db, rows)
                stats.protocols_synced += 1
                stats.price_rows += count
            except Exception as e:
                logger.error("Protocol sync failed for %s: %s", protocol, e)
                stats.failures.append(f"protocol:{protocol}:{e}")

        # ── Chains ──
        for item in get_watchlist(db, asset_class="chain"):
            chain = item["symbol"]
            try:
                rows = artemis.get_chain_metrics(chain, days=days)
                count = upsert_chain_daily(db, rows)
                stats.chains_synced += 1
                stats.price_rows += count
            except Exception as e:
                logger.error("Chain sync failed for %s: %s", chain, e)
                stats.failures.append(f"chain:{chain}:{e}")

        # ── Token liquidity (for crypto watchlist items) ──
        for item in get_watchlist(db, asset_class="crypto"):
            symbol = item["symbol"]
            chain = (item.get("meta") or "{}") if isinstance(item.get("meta"), str) else "{}"
            import json
            meta = json.loads(chain) if isinstance(chain, str) else (chain or {})
            target_chain = meta.get("chain", "ethereum")
            try:
                rows = artemis.get_token_liquidity(symbol, target_chain, days=days)
                if rows:
                    count = upsert_token_liquidity(db, rows)
                    stats.liquidity_synced += 1
                    stats.price_rows += count
            except Exception as e:
                logger.error("Liquidity sync failed for %s: %s", symbol, e)
                stats.failures.append(f"liquidity:{symbol}:{e}")

    return stats
