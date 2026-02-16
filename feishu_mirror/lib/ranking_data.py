"""NASDAQ & Crypto daily ranking data + Feishu card builder."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ── Data classes ──


@dataclass
class RankingItem:
    rank: int
    symbol: str
    name: str
    price: float | None
    change_pct: float | None


@dataclass
class RankingResult:
    category: str  # nasdaq_gainers / nasdaq_losers / crypto_gainers / crypto_losers
    items: list[RankingItem] = field(default_factory=list)
    fetch_time: str = ""
    error: str | None = None


# ── NASDAQ (market-cap top 100 → change % top 5) ──


def fetch_nasdaq_rankings() -> tuple[RankingResult, RankingResult]:
    """Fetch NASDAQ market-cap top 100, then pick top 5 gainers & losers."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    gainers = RankingResult(category="nasdaq_gainers", fetch_time=now)
    losers = RankingResult(category="nasdaq_losers", fetch_time=now)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(
            "https://api.nasdaq.com/api/screener/stocks",
            params={
                "exchange": "NASDAQ",
                "limit": 100,
                "sortcolumn": "marketCap",
                "sortorder": "desc",
            },
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", {}).get("table", {}).get("rows", [])

        parsed = []
        for row in rows:
            pct_str = row.get("pctchange", "0").replace("%", "").replace(",", "")
            try:
                pct = float(pct_str)
            except (ValueError, TypeError):
                continue
            price_str = row.get("lastsale", "$0").replace("$", "").replace(",", "")
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = None
            parsed.append((row, price, pct))

        parsed.sort(key=lambda x: x[2], reverse=True)
        gainers.items = [
            RankingItem(rank=i, symbol=r.get("symbol", ""), name=r.get("name", "")[:20], price=p, change_pct=pct)
            for i, (r, p, pct) in enumerate(parsed[:5], 1)
        ]
        losers.items = [
            RankingItem(rank=i, symbol=r.get("symbol", ""), name=r.get("name", "")[:20], price=p, change_pct=pct)
            for i, (r, p, pct) in enumerate(parsed[-5:], 1)
        ]

    except Exception as e:
        logger.error("NASDAQ fetch failed: %s", e)
        gainers.error = str(e)
        losers.error = str(e)

    return gainers, losers


# ── Crypto (CoinGecko market-cap top 100 → change % top 5) ──


def fetch_crypto_rankings(artemis_api_key: str = "") -> tuple[RankingResult, RankingResult]:
    """Fetch crypto market-cap top 100 via CoinGecko, then pick top 5 gainers & losers."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    gainers = RankingResult(category="crypto_gainers", fetch_time=now)
    losers = RankingResult(category="crypto_losers", fetch_time=now)

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "24h",
                "sparkline": "false",
            },
            timeout=15,
        )
        resp.raise_for_status()
        coins = resp.json()

        valid = [
            c for c in coins
            if c.get("price_change_percentage_24h") is not None
        ]
        valid.sort(key=lambda c: c["price_change_percentage_24h"], reverse=True)

        gainers.items = [
            RankingItem(
                rank=i,
                symbol=c["symbol"].upper(),
                name=c.get("name", "")[:20],
                price=c.get("current_price"),
                change_pct=round(c["price_change_percentage_24h"], 2),
            )
            for i, c in enumerate(valid[:5], 1)
        ]
        losers.items = [
            RankingItem(
                rank=i,
                symbol=c["symbol"].upper(),
                name=c.get("name", "")[:20],
                price=c.get("current_price"),
                change_pct=round(c["price_change_percentage_24h"], 2),
            )
            for i, c in enumerate(valid[-5:], 1)
        ]

    except Exception as e:
        logger.error("Crypto rankings fetch failed: %s", e)
        gainers.error = str(e)
        losers.error = str(e)

    return gainers, losers


# ── Market Pulse (customizable watchlist) ──


@dataclass
class PulseItem:
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    asset_class: str  # "stock" or "crypto"


# Artemis symbol mapping for crypto pulse items
_CRYPTO_ARTEMIS_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "ADA": "cardano", "AVAX": "avalanche", "DOT": "polkadot",
    "LINK": "chainlink", "UNI": "uniswap", "AAVE": "aave",
    "ARB": "arbitrum", "OP": "optimism",
}

DEFAULT_PULSE = [
    # (symbol, asset_class, display_name, row)
    ("BTC", "crypto", "BTC", 1),
    ("ETH", "crypto", "ETH", 1),
    ("HOOD", "stock", "Robinhood", 1),
    ("COIN", "stock", "Coinbase", 1),
    ("NVDA", "stock", "NVIDIA", 2),
    ("MSFT", "stock", "Microsoft", 2),
    ("GOOGL", "stock", "Google", 2),
    ("META", "stock", "Meta", 2),
]


def seed_default_pulse(db) -> None:
    """Seed the default 8 pulse items into the watchlist (idempotent)."""
    from .db_market import get_watchlist, upsert_watchlist

    rows = get_watchlist(db, enabled_only=False)
    existing_pulse = {r["symbol"] for r in rows if r.get("label") == "pulse"}
    if existing_pulse:
        return  # already seeded

    for sym, ac, display, row in DEFAULT_PULSE:
        upsert_watchlist(db, symbol=sym, asset_class=ac, label="pulse",
                         meta={"display": display, "row": row})
    logger.info("Seeded %d default pulse items", len(DEFAULT_PULSE))


def fetch_market_pulse(artemis_api_key: str, db=None) -> list[PulseItem]:
    """Fetch pulse assets from watchlist (label=pulse). Falls back to defaults."""
    from .market_api import YFinanceClient

    # Resolve pulse config: DB watchlist or hardcoded defaults
    pulse_config: list[tuple[str, str, str, int]] = []
    if db:
        from .db_market import get_watchlist
        rows = get_watchlist(db, enabled_only=True)
        pulse_rows = [r for r in rows if r.get("label") == "pulse"]
        if pulse_rows:
            for r in pulse_rows:
                meta = r.get("meta") or {}
                if isinstance(meta, str):
                    import json
                    meta = json.loads(meta)
                pulse_config.append((
                    r["symbol"],
                    r["asset_class"],
                    meta.get("display", r["symbol"]),
                    meta.get("row", 1),
                ))
    if not pulse_config:
        pulse_config = [(s, a, d, r) for s, a, d, r in DEFAULT_PULSE]

    # Sort by row then original order
    pulse_config.sort(key=lambda x: x[3])

    # Fetch quotes
    artemis_client = None
    if artemis_api_key:
        try:
            from .market_api import ArtemisClient
            artemis_client = ArtemisClient(artemis_api_key)
        except Exception as e:
            logger.warning("Artemis client init failed: %s", e)

    yf = YFinanceClient()
    items: list[PulseItem] = []

    for ticker, asset_class, display, _row in pulse_config:
        try:
            if asset_class == "crypto" and artemis_client:
                artemis_sym = _CRYPTO_ARTEMIS_MAP.get(ticker.upper(), ticker.lower())
                quote = artemis_client.get_crypto_quote(artemis_sym)
            else:
                quote = yf.get_quote(ticker)
            if quote:
                items.append(PulseItem(
                    symbol=display, name=display,
                    price=quote["price"], change_pct=quote["change_pct"],
                    asset_class=asset_class,
                ))
        except Exception as e:
            logger.warning("Pulse fetch failed for %s: %s", ticker, e)

    return items


# ── Feishu Card Builder (Schema 2.0, visually rich) ──


def _fmt_price(price: float | None) -> str:
    if price is None:
        return "-"
    if price >= 1000:
        return f"${price:,.0f}"
    if price >= 1:
        return f"${price:.2f}"
    if price >= 0.001:
        return f"${price:.4f}"
    if price >= 0.000001:
        return f"${price:.8f}"
    return f"${price:.2e}"


def _fmt_pct_colored(pct: float | None) -> str:
    """Format percentage with <font color> for Feishu markdown."""
    if pct is None:
        return "-"
    sign = "+" if pct > 0 else ""
    color = "green" if pct >= 0 else "red"
    return f"<font color='{color}'>{sign}{pct:.2f}%</font>"


def _fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "-"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def _pulse_column(item: PulseItem) -> dict:
    """Build a single column for a pulse item (BTC, ETH, etc.)."""
    indicator = "\U0001F7E2" if (item.change_pct or 0) >= 0 else "\U0001F534"
    return {
        "tag": "column",
        "width": "weighted",
        "weight": 1,
        "elements": [{
            "tag": "markdown",
            "content": (
                f"{indicator} **{item.symbol}**\n"
                f"{_fmt_price(item.price)}\n"
                f"{_fmt_pct_colored(item.change_pct)}"
            ),
        }],
    }


def _ranking_items_md(result: RankingResult, limit: int = 5) -> str:
    """Format ranking items as visually rich compact markdown."""
    if result.error:
        return f"\u26A0\uFE0F 数据暂不可用"
    if not result.items:
        return "暂无数据"

    medals = {1: "\U0001F947", 2: "\U0001F948", 3: "\U0001F949"}
    lines = []
    for item in result.items[:limit]:
        rank_str = medals.get(item.rank, f"**{item.rank}.**")
        pct_str = _fmt_pct_colored(item.change_pct)
        lines.append(f"{rank_str} **{item.symbol}**  {_fmt_price(item.price)}  {pct_str}")
    return "\n".join(lines)


def _build_market_column(title: str, rankings: list[RankingResult]) -> list[dict]:
    """Build elements for one column (NASDAQ or Crypto)."""
    elements: list[dict] = [{"tag": "markdown", "content": f"**{title}**"}]

    for r in rankings:
        is_gainer = "gainers" in r.category
        label = "\U0001F3C6 涨幅 TOP 5" if is_gainer else "\U0001F4A7 跌幅 TOP 5"
        elements.append({"tag": "markdown", "content": f"\n{label}"})
        elements.append({"tag": "markdown", "content": _ranking_items_md(r)})

    return elements


def _determine_header_template(rankings: list[RankingResult]) -> str:
    """Pick header color based on overall market sentiment."""
    total_pct = 0.0
    count = 0
    for r in rankings:
        for item in r.items[:5]:
            if item.change_pct is not None:
                total_pct += item.change_pct
                count += 1
    avg = total_pct / count if count else 0
    if avg > 1:
        return "green"
    if avg < -1:
        return "red"
    return "indigo"


def build_ranking_card(
    rankings: list[RankingResult],
    date_str: str,
    pulse: list[PulseItem] | None = None,
) -> dict:
    """Build a visually rich Feishu interactive card (Schema 2.0)."""
    elements: list[dict] = []

    # ── Market Pulse: key assets at a glance (2 rows of 4) ──
    if pulse:
        row1 = pulse[:4]
        row2 = pulse[4:8]

        if row1:
            elements.append({
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [_pulse_column(p) for p in row1],
            })
        if row2:
            elements.append({
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [_pulse_column(p) for p in row2],
            })
        elements.append({"tag": "hr"})

    # ── Rankings: two-column (NASDAQ | Crypto) ──
    nasdaq = [r for r in rankings if "nasdaq" in r.category]
    crypto = [r for r in rankings if "crypto" in r.category]

    if nasdaq and crypto:
        elements.append({
            "tag": "column_set",
            "flex_mode": "bisect",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": _build_market_column("\U0001F4C8 美股 NASDAQ", nasdaq),
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": _build_market_column("\U0001F4B0 加密货币", crypto),
                },
            ],
        })
    else:
        for r in rankings:
            elements.append({"tag": "markdown", "content": f"**{r.category}**"})
            elements.append({"tag": "markdown", "content": _ranking_items_md(r, limit=10)})
            elements.append({"tag": "hr"})
        if elements and elements[-1].get("tag") == "hr":
            elements.pop()

    # ── Footer ──
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "markdown",
        "content": f"\U0001F4E1 {date_str} \u00B7 NASDAQ Top 100 \u00B7 CoinGecko Top 100 \u00B7 Powered by **\u8D1D\u591A\u591A**",
    })

    template = _determine_header_template(rankings)

    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"\U0001F4CA \u6BCF\u65E5\u5E02\u573A\u8109\u640F \u00B7 {date_str}"},
            "subtitle": {"tag": "plain_text", "content": "Daily Market Pulse \u00B7 \u8D1D\u591A\u591A"},
            "template": template,
        },
        "body": {
            "elements": elements,
        },
    }
