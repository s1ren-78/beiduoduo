"""Database operations for market, financial, and on-chain data tables."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from .db import DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _upsert_batch(
    db: DB,
    rows: list[dict[str, Any]],
    sql: str,
    param_fn: Callable[[dict[str, Any], str], tuple],
) -> int:
    """Generic batch upsert: guard empty → _now_iso → with conn → for row → execute."""
    if not rows:
        return 0
    now = _now_iso()
    with db.conn() as conn:
        for r in rows:
            conn.execute(sql, param_fn(r, now))
    return len(rows)


def _query_latest(db: DB, sql: str, params: tuple) -> list[dict[str, Any]]:
    """Generic query returning list of rows."""
    with db.conn() as conn:
        return conn.execute(sql, params).fetchall()


# ── Watchlist ──


def upsert_watchlist(db: DB, symbol: str, asset_class: str, label: str | None = None, enabled: bool = True, meta: dict | None = None) -> int:
    now = _now_iso()
    meta_str = json.dumps(meta or {}, ensure_ascii=False)
    with db.conn() as conn:
        conn.execute(
            """
            INSERT INTO market_watchlist(symbol, asset_class, label, enabled, meta, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, asset_class)
            DO UPDATE SET label = excluded.label,
                          enabled = excluded.enabled,
                          meta = excluded.meta,
                          updated_at = excluded.updated_at
            """,
            (symbol.upper(), asset_class, label, 1 if enabled else 0, meta_str, now, now),
        )
        cur = conn.execute(
            "SELECT id FROM market_watchlist WHERE symbol = ? AND asset_class = ?",
            (symbol.upper(), asset_class),
        )
        return int(cur.fetchone()["id"])


def get_watchlist(db: DB, asset_class: str | None = None, enabled_only: bool = True) -> list[dict[str, Any]]:
    with db.conn() as conn:
        sql = "SELECT * FROM market_watchlist WHERE 1=1"
        params: list[Any] = []
        if enabled_only:
            sql += " AND enabled = 1"
        if asset_class:
            sql += " AND asset_class = ?"
            params.append(asset_class)
        sql += " ORDER BY id ASC"
        return conn.execute(sql, params).fetchall()


# ── Market Price Daily ──

_PRICE_DAILY_SQL = """
INSERT INTO market_price_daily(symbol, asset_class, trade_date, open, high, low, close, volume, market_cap, meta, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (symbol, asset_class, trade_date)
DO UPDATE SET open = excluded.open, high = excluded.high, low = excluded.low,
              close = excluded.close, volume = excluded.volume,
              market_cap = excluded.market_cap, meta = excluded.meta
"""


def upsert_price_daily(db: DB, rows: list[dict[str, Any]]) -> int:
    return _upsert_batch(db, rows, _PRICE_DAILY_SQL, lambda r, now: (
        r["symbol"], r["asset_class"], r["trade_date"],
        r.get("open"), r.get("high"), r.get("low"), r.get("close"),
        r.get("volume"), r.get("market_cap"),
        json.dumps(r.get("meta", {}), ensure_ascii=False), now,
    ))


def query_price_daily(db: DB, symbol: str, asset_class: str, days: int = 30) -> list[dict[str, Any]]:
    return _query_latest(db, """
        SELECT * FROM market_price_daily
        WHERE symbol = ? AND asset_class = ?
        ORDER BY trade_date DESC LIMIT ?
    """, (symbol.upper(), asset_class, days))


# ── Market Quote Latest ──


def upsert_quote_latest(db: DB, symbol: str, asset_class: str, price: float | None, change_pct: float | None, volume: float | None, market_cap: float | None, meta: dict | None = None) -> None:
    now = _now_iso()
    meta_str = json.dumps(meta or {}, ensure_ascii=False)
    with db.conn() as conn:
        conn.execute(
            """
            INSERT INTO market_quote_latest(symbol, asset_class, price, change_pct, volume, market_cap, updated_at, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, asset_class)
            DO UPDATE SET price = excluded.price,
                          change_pct = excluded.change_pct,
                          volume = excluded.volume,
                          market_cap = excluded.market_cap,
                          updated_at = excluded.updated_at,
                          meta = excluded.meta
            """,
            (symbol.upper(), asset_class, price, change_pct, volume, market_cap, now, meta_str),
        )


def get_quote_latest(db: DB, symbol: str, asset_class: str) -> dict[str, Any] | None:
    with db.conn() as conn:
        cur = conn.execute(
            "SELECT * FROM market_quote_latest WHERE symbol = ? AND asset_class = ?",
            (symbol.upper(), asset_class),
        )
        return cur.fetchone()


# ── Financial Statements ──

_FIN_STATEMENT_SQL = """
INSERT INTO fin_statement(entity_id, entity_type, period, period_type, metric, value, unit, meta, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (entity_id, entity_type, period, metric)
DO UPDATE SET value = excluded.value, unit = excluded.unit,
              period_type = excluded.period_type, meta = excluded.meta
"""


def upsert_fin_statement(db: DB, rows: list[dict[str, Any]]) -> int:
    return _upsert_batch(db, rows, _FIN_STATEMENT_SQL, lambda r, now: (
        r["entity_id"], r["entity_type"], r["period"], r["period_type"],
        r["metric"], r.get("value"), r.get("unit"),
        json.dumps(r.get("meta", {}), ensure_ascii=False), now,
    ))


def query_fin_statement(db: DB, entity_id: str, entity_type: str, limit: int = 8) -> list[dict[str, Any]]:
    return _query_latest(db, """
        SELECT * FROM fin_statement
        WHERE entity_id = ? AND entity_type = ?
        ORDER BY period DESC LIMIT ?
    """, (entity_id.upper(), entity_type, limit))


# ── On-chain Protocol Daily ──

_PROTOCOL_DAILY_SQL = """
INSERT INTO onchain_protocol_daily(protocol, metric_date, tvl, revenue, fees, active_users, transactions, meta, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (protocol, metric_date)
DO UPDATE SET tvl = excluded.tvl, revenue = excluded.revenue, fees = excluded.fees,
              active_users = excluded.active_users, transactions = excluded.transactions,
              meta = excluded.meta
"""


def upsert_protocol_daily(db: DB, rows: list[dict[str, Any]]) -> int:
    return _upsert_batch(db, rows, _PROTOCOL_DAILY_SQL, lambda r, now: (
        r["protocol"], r["metric_date"],
        r.get("tvl"), r.get("revenue"), r.get("fees"),
        r.get("active_users"), r.get("transactions"),
        json.dumps(r.get("meta", {}), ensure_ascii=False), now,
    ))


def query_protocol_daily(db: DB, protocol: str, days: int = 30) -> list[dict[str, Any]]:
    return _query_latest(db, """
        SELECT * FROM onchain_protocol_daily
        WHERE protocol = ? ORDER BY metric_date DESC LIMIT ?
    """, (protocol.lower(), days))


# ── On-chain Chain Daily ──

_CHAIN_DAILY_SQL = """
INSERT INTO onchain_chain_daily(chain, metric_date, gas_used, tps, active_addresses, transaction_count, tvl, meta, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (chain, metric_date)
DO UPDATE SET gas_used = excluded.gas_used, tps = excluded.tps,
              active_addresses = excluded.active_addresses,
              transaction_count = excluded.transaction_count,
              tvl = excluded.tvl, meta = excluded.meta
"""


def upsert_chain_daily(db: DB, rows: list[dict[str, Any]]) -> int:
    return _upsert_batch(db, rows, _CHAIN_DAILY_SQL, lambda r, now: (
        r["chain"], r["metric_date"],
        r.get("gas_used"), r.get("tps"),
        r.get("active_addresses"), r.get("transaction_count"),
        r.get("tvl"),
        json.dumps(r.get("meta", {}), ensure_ascii=False), now,
    ))


def query_chain_daily(db: DB, chain: str, days: int = 30) -> list[dict[str, Any]]:
    return _query_latest(db, """
        SELECT * FROM onchain_chain_daily
        WHERE chain = ? ORDER BY metric_date DESC LIMIT ?
    """, (chain.lower(), days))


# ── On-chain Token Liquidity ──

_TOKEN_LIQUIDITY_SQL = """
INSERT INTO onchain_token_liquidity(token, chain, metric_date, pool_count, total_liquidity_usd, volume_24h, meta, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (token, chain, metric_date)
DO UPDATE SET pool_count = excluded.pool_count,
              total_liquidity_usd = excluded.total_liquidity_usd,
              volume_24h = excluded.volume_24h, meta = excluded.meta
"""


def upsert_token_liquidity(db: DB, rows: list[dict[str, Any]]) -> int:
    return _upsert_batch(db, rows, _TOKEN_LIQUIDITY_SQL, lambda r, now: (
        r["token"], r["chain"], r["metric_date"],
        r.get("pool_count"), r.get("total_liquidity_usd"),
        r.get("volume_24h"),
        json.dumps(r.get("meta", {}), ensure_ascii=False), now,
    ))


def query_token_liquidity(db: DB, token: str, chain: str, days: int = 30) -> list[dict[str, Any]]:
    return _query_latest(db, """
        SELECT * FROM onchain_token_liquidity
        WHERE token = ? AND chain = ?
        ORDER BY metric_date DESC LIMIT ?
    """, (token.upper(), chain.lower(), days))
