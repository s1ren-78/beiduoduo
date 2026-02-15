"""NASDAQ & Crypto daily ranking data + Feishu card builder."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Top crypto tokens tracked (Artemis identifiers) ──

TOP_CRYPTO_TOKENS: list[str] = [
    "bitcoin", "ethereum", "solana", "cardano", "avalanche",
    "polkadot", "chainlink", "uniswap", "aave", "arbitrum",
    "optimism", "polygon", "near", "aptos", "sui",
    "celestia", "injective", "sei", "starknet", "jupiter",
    "render", "filecoin", "the-graph", "lido", "eigenlayer",
    "maker", "compound", "synthetix", "curve", "pendle",
    "ethena", "jito", "raydium", "ondo", "worldcoin",
    "pepe", "dogecoin", "shiba-inu", "bonk", "floki",
    "toncoin", "tron", "litecoin", "bitcoin-cash", "stellar",
    "hedera", "algorand", "cosmos", "internet-computer", "mantle",
]

BATCH_SIZE = 10  # tokens per Artemis API call


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


# ── Helpers ──


def _build_nasdaq_items(parsed: list[tuple]) -> list[RankingItem]:
    """Convert parsed NASDAQ rows to ranked items."""
    return [
        RankingItem(rank=i, symbol=row.get("symbol", ""), name=row.get("name", "")[:20], price=price, change_pct=pct)
        for i, (row, price, pct) in enumerate(parsed, 1)
    ]


def _build_crypto_items(quotes: list[dict[str, Any]]) -> list[RankingItem]:
    """Convert crypto quote dicts to ranked items."""
    return [
        RankingItem(rank=i, symbol=q["symbol"].upper(), name=q["symbol"].replace("-", " ").title(), price=q["price"], change_pct=q["change_pct"])
        for i, q in enumerate(quotes, 1)
    ]


# ── NASDAQ ──


def fetch_nasdaq_rankings() -> tuple[RankingResult, RankingResult]:
    """Fetch NASDAQ top 10 gainers and losers from public screener API."""
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
            params={"exchange": "NASDAQ", "limit": 200},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", {}).get("table", {}).get("rows", [])

        # Parse all rows, sort locally (API ignores sort params)
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

        # Top 10 gainers (highest % change) / Top 10 losers (lowest % change)
        parsed.sort(key=lambda x: x[2], reverse=True)
        gainers.items = _build_nasdaq_items(parsed[:10])
        losers.items = _build_nasdaq_items(parsed[-10:])

    except Exception as e:
        logger.error("NASDAQ fetch failed: %s", e)
        gainers.error = str(e)
        losers.error = str(e)

    return gainers, losers


# ── Crypto ──


def fetch_crypto_rankings(artemis_api_key: str) -> tuple[RankingResult, RankingResult]:
    """Fetch crypto top 10 gainers and losers using Artemis price data."""
    from .market_api import ArtemisClient

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    gainers = RankingResult(category="crypto_gainers", fetch_time=now)
    losers = RankingResult(category="crypto_losers", fetch_time=now)

    if not artemis_api_key:
        gainers.error = "ARTEMIS_API_KEY not set"
        losers.error = "ARTEMIS_API_KEY not set"
        return gainers, losers

    try:
        client = ArtemisClient(artemis_api_key)
        end = datetime.utcnow()
        start = end - timedelta(days=2)

        # Fetch in batches
        all_quotes: list[dict[str, Any]] = []
        for i in range(0, len(TOP_CRYPTO_TOKENS), BATCH_SIZE):
            batch = TOP_CRYPTO_TOKENS[i : i + BATCH_SIZE]
            symbols_str = ",".join(batch)
            try:
                data = client._fetch("price", symbols_str, start, end)
                for sym in batch:
                    series = data.get(sym, {}).get("price", [])
                    if isinstance(series, str):
                        continue
                    valid = [p for p in (series or []) if p.get("val") is not None]
                    if len(valid) < 2:
                        continue
                    latest = valid[-1]["val"]
                    prev = valid[-2]["val"]
                    if prev and prev != 0:
                        pct = round((latest - prev) / prev * 100, 2)
                        all_quotes.append({
                            "symbol": sym,
                            "price": latest,
                            "change_pct": pct,
                        })
            except Exception as e:
                logger.warning("Artemis batch fetch failed for %s: %s", symbols_str, e)

        all_quotes.sort(key=lambda q: q["change_pct"], reverse=True)
        bottom = list(reversed(all_quotes[-10:])) if len(all_quotes) >= 10 else list(reversed(all_quotes))
        gainers.items = _build_crypto_items(all_quotes[:10])
        losers.items = _build_crypto_items(bottom)

    except Exception as e:
        logger.error("Crypto rankings fetch failed: %s", e)
        gainers.error = str(e)
        losers.error = str(e)

    return gainers, losers


# ── Feishu Card Builder ──


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


def _fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "-"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def _ranking_markdown(result: RankingResult) -> str:
    """Build a markdown table for one ranking section."""
    if result.error:
        return f"*{result.category}*: Data unavailable ({result.error})"
    if not result.items:
        return f"*{result.category}*: No data"

    lines = ["| # | Symbol | Price | Change |", "| --- | --- | --- | --- |"]
    for item in result.items:
        lines.append(
            f"| {item.rank} | **{item.symbol}** | {_fmt_price(item.price)} | {_fmt_pct(item.change_pct)} |"
        )
    return "\n".join(lines)


def _section_title(category: str) -> str:
    titles = {
        "nasdaq_gainers": "NASDAQ Top Gainers",
        "nasdaq_losers": "NASDAQ Top Losers",
        "crypto_gainers": "Crypto Top Gainers",
        "crypto_losers": "Crypto Top Losers",
    }
    return titles.get(category, category)


def _section_emoji(category: str) -> str:
    emojis = {
        "nasdaq_gainers": "\U0001F4C8",
        "nasdaq_losers": "\U0001F4C9",
        "crypto_gainers": "\U0001F680",
        "crypto_losers": "\U0001F534",
    }
    return emojis.get(category, "")


def build_ranking_card(rankings: list[RankingResult], date_str: str) -> dict:
    """Build a Feishu interactive card with all ranking sections."""
    elements: list[dict] = []

    for result in rankings:
        # Section header
        elements.append({
            "tag": "markdown",
            "content": f"**{_section_emoji(result.category)} {_section_title(result.category)}**",
        })
        # Table
        elements.append({
            "tag": "markdown",
            "content": _ranking_markdown(result),
        })
        # Divider between sections
        elements.append({"tag": "hr"})

    # Remove last divider
    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    # Footer note
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"Data as of {date_str} | Powered by Beiduoduo"},
        ],
    })

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"Daily Market Rankings - {date_str}"},
            "template": "blue",
        },
        "elements": elements,
    }
