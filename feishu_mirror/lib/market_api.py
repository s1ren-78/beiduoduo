"""API clients for YFinance (stocks) and Artemis (crypto/on-chain)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ── YFinance Client ──


class YFinanceClient:
    """Wraps yfinance for stock OHLCV data."""

    def get_history(self, symbol: str, days: int = 365) -> list[dict[str, Any]]:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        period = f"{days}d" if days <= 730 else "max"
        df = ticker.history(period=period)
        if df.empty:
            return []
        rows = []
        for date, row in df.iterrows():
            rows.append({
                "symbol": symbol.upper(),
                "asset_class": "stock",
                "trade_date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4) if row["Open"] == row["Open"] else None,
                "high": round(float(row["High"]), 4) if row["High"] == row["High"] else None,
                "low": round(float(row["Low"]), 4) if row["Low"] == row["Low"] else None,
                "close": round(float(row["Close"]), 4) if row["Close"] == row["Close"] else None,
                "volume": float(row["Volume"]) if row["Volume"] == row["Volume"] else None,
                "market_cap": None,
                "meta": {},
            })
        return rows

    def get_quote(self, symbol: str) -> dict[str, Any] | None:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or "regularMarketPrice" not in info:
            return None
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        change_pct = None
        if price and prev_close and prev_close != 0:
            change_pct = round((price - prev_close) / prev_close * 100, 4)
        return {
            "symbol": symbol.upper(),
            "asset_class": "stock",
            "price": price,
            "change_pct": change_pct,
            "volume": info.get("regularMarketVolume") or info.get("volume"),
            "market_cap": info.get("marketCap"),
            "meta": {
                "name": info.get("shortName"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
            },
        }


# ── Artemis Client ──


def _extract_metric_series(symbols_data: dict, symbol: str, metric: str) -> list[dict]:
    """Extract time series from Artemis response: data.symbols.{symbol}.{metric}"""
    sym_data = symbols_data.get(symbol, {})
    series = sym_data.get(metric)
    if isinstance(series, str):
        # "Metric not available for asset."
        return []
    return series or []


class ArtemisClient:
    """Wraps Artemis SDK for crypto prices and on-chain data."""

    def __init__(self, api_key: str) -> None:
        from artemis import Artemis
        self.api_key = api_key
        self.client = Artemis(api_key=api_key)

    def _fetch(self, metrics: str, symbols: str, start: datetime, end: datetime) -> dict:
        try:
            result = self.client.fetch_metrics(
                metrics,
                api_key=self.api_key,
                symbols=symbols,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
            )
            return result.to_dict().get("data", {}).get("symbols", {})
        except Exception as e:
            logger.warning("Artemis fetch failed (%s, %s): %s", metrics, symbols, e)
            return {}

    # ── Crypto price data ──

    def get_crypto_history(self, symbol: str, days: int = 365) -> list[dict[str, Any]]:
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        # Artemis uses full asset names for some (bitcoin, ethereum, solana)
        artemis_sym = self._normalize_symbol(symbol)
        data = self._fetch("price,mc", artemis_sym, start, end)

        prices = _extract_metric_series(data, artemis_sym, "price")
        mcs = _extract_metric_series(data, artemis_sym, "mc")
        mc_map = {p["date"]: p.get("val") for p in mcs}

        rows = []
        for point in prices:
            val = point.get("val")
            if val is None:
                continue
            rows.append({
                "symbol": symbol.upper(),
                "asset_class": "crypto",
                "trade_date": point["date"],
                "open": None,
                "high": None,
                "low": None,
                "close": val,
                "volume": None,
                "market_cap": mc_map.get(point["date"]),
                "meta": {},
            })
        return rows

    def get_crypto_quote(self, symbol: str) -> dict[str, Any] | None:
        end = datetime.utcnow()
        start = end - timedelta(days=2)
        artemis_sym = self._normalize_symbol(symbol)
        data = self._fetch("price,mc", artemis_sym, start, end)

        prices = _extract_metric_series(data, artemis_sym, "price")
        mcs = _extract_metric_series(data, artemis_sym, "mc")
        if not prices:
            return None

        # Find latest non-null price
        valid = [p for p in prices if p.get("val") is not None]
        if not valid:
            return None
        latest = valid[-1]
        prev = valid[-2] if len(valid) >= 2 else None

        price = latest["val"]
        change_pct = None
        if prev and prev["val"] and prev["val"] != 0:
            change_pct = round((price - prev["val"]) / prev["val"] * 100, 4)

        mc_map = {p["date"]: p.get("val") for p in mcs}
        return {
            "symbol": symbol.upper(),
            "asset_class": "crypto",
            "price": price,
            "change_pct": change_pct,
            "volume": None,
            "market_cap": mc_map.get(latest["date"]),
            "meta": {},
        }

    # ── Protocol metrics ──

    def get_protocol_metrics(self, protocol: str, days: int = 30) -> list[dict[str, Any]]:
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        artemis_sym = protocol.lower()
        data = self._fetch("tvl,revenue,fees", artemis_sym, start, end)

        tvls = _extract_metric_series(data, artemis_sym, "tvl")
        revs = _extract_metric_series(data, artemis_sym, "revenue")
        fees = _extract_metric_series(data, artemis_sym, "fees")

        # Merge by date
        dates = sorted({p["date"] for series in [tvls, revs, fees] for p in series})
        tvl_map = {p["date"]: p.get("val") for p in tvls}
        rev_map = {p["date"]: p.get("val") for p in revs}
        fee_map = {p["date"]: p.get("val") for p in fees}

        rows = []
        for d in dates:
            rows.append({
                "protocol": artemis_sym,
                "metric_date": d,
                "tvl": tvl_map.get(d),
                "revenue": rev_map.get(d),
                "fees": fee_map.get(d),
                "active_users": None,
                "transactions": None,
                "meta": {},
            })
        return rows

    # ── Chain metrics ──

    def get_chain_metrics(self, chain: str, days: int = 30) -> list[dict[str, Any]]:
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        artemis_sym = chain.lower()
        data = self._fetch("tvl,txns", artemis_sym, start, end)

        tvls = _extract_metric_series(data, artemis_sym, "tvl")
        txns = _extract_metric_series(data, artemis_sym, "txns")

        dates = sorted({p["date"] for series in [tvls, txns] for p in series})
        tvl_map = {p["date"]: p.get("val") for p in tvls}
        txn_map = {p["date"]: p.get("val") for p in txns}

        rows = []
        for d in dates:
            rows.append({
                "chain": artemis_sym,
                "metric_date": d,
                "gas_used": None,
                "tps": None,
                "active_addresses": None,
                "transaction_count": int(txn_map[d]) if txn_map.get(d) is not None else None,
                "tvl": tvl_map.get(d),
                "meta": {},
            })
        return rows

    # ── Token liquidity (not directly available via SDK, skip gracefully) ──

    def get_token_liquidity(self, token: str, chain: str, days: int = 30) -> list[dict[str, Any]]:
        # Artemis SDK doesn't expose a dedicated liquidity endpoint;
        # return empty for now — can be extended when the API supports it.
        return []

    # ── Protocol financials (revenue/fees as financial statements) ──

    def get_protocol_financials(self, protocol: str) -> list[dict[str, Any]]:
        end = datetime.utcnow()
        start = end - timedelta(days=365)
        artemis_sym = protocol.lower()
        data = self._fetch("revenue,fees", artemis_sym, start, end)

        revs = _extract_metric_series(data, artemis_sym, "revenue")
        fees = _extract_metric_series(data, artemis_sym, "fees")

        rows = []
        for point in revs:
            if point.get("val") is not None:
                rows.append({
                    "entity_id": artemis_sym,
                    "entity_type": "protocol",
                    "period": point["date"],
                    "period_type": "weekly",
                    "metric": "revenue",
                    "value": point["val"],
                    "unit": "USD",
                    "meta": {},
                })
        for point in fees:
            if point.get("val") is not None:
                rows.append({
                    "entity_id": artemis_sym,
                    "entity_type": "protocol",
                    "period": point["date"],
                    "period_type": "weekly",
                    "metric": "fees",
                    "value": point["val"],
                    "unit": "USD",
                    "meta": {},
                })
        return rows

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Map common ticker symbols to Artemis identifiers."""
        mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "AVAX": "avalanche",
            "MATIC": "polygon",
            "DOT": "polkadot",
            "ADA": "cardano",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "AAVE": "aave",
            "ARB": "arbitrum",
            "OP": "optimism",
        }
        return mapping.get(symbol.upper(), symbol.lower())
