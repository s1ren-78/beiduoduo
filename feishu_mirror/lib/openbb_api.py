"""
OpenBB-style data layer — macro, equity enhanced fundamentals, forex, options.

Uses yfinance (direct), fredapi, and FMP REST API for maximum reliability.
OpenBB SDK has yfinance version conflicts, so we call the providers directly.
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional

import requests
import yfinance as yf


# ── TTL Cache decorator ─────────────────────────────────────────────────
def _ttl_cache(seconds: int):
    """Simple TTL cache for functions with hashable args."""
    def decorator(fn):
        _cache: dict[tuple, tuple[float, Any]] = {}
        _lock = threading.Lock()
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = _time.time()
            with _lock:
                if key in _cache:
                    ts, val = _cache[key]
                    if now - ts < seconds:
                        return val
            result = fn(*args, **kwargs)
            with _lock:
                _cache[key] = (now, result)
            return result
        wrapper.cache_clear = lambda: _cache.clear()
        return wrapper
    return decorator


@lru_cache(maxsize=64)
def _get_ticker(symbol: str) -> yf.Ticker:
    """Reuse yf.Ticker instances to avoid recreating HTTP sessions."""
    return yf.Ticker(symbol)

_log = logging.getLogger(__name__)

# ── FRED (macro) ──────────────────────────────────────────────────────────

FRED_SERIES_MAP = {
    "GDP": "GDP",
    "CPI": "CPIAUCSL",
    "FEDFUNDS": "FEDFUNDS",
    "UNRATE": "UNRATE",
    "DGS10": "DGS10",
    "M2SL": "M2SL",
    "联邦基金利率": "FEDFUNDS",
    "失业率": "UNRATE",
    "10年国债": "DGS10",
    "M2货币供应": "M2SL",
}


def _get_fred():
    """Lazy-load fredapi.Fred with API key."""
    from fredapi import Fred
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        raise ValueError("FRED_API_KEY not set — 请在 .env 中设置（https://fred.stlouisfed.org/docs/api/api_key.html 免费申请）")
    return Fred(api_key=key)


@_ttl_cache(seconds=3600)
def get_macro_indicator(series_id: str, days: int = 365) -> list[dict]:
    """Fetch a single FRED series. series_id can be an alias (GDP/CPI/...) or raw FRED ID."""
    resolved = FRED_SERIES_MAP.get(series_id.upper(), series_id.upper())
    fred = _get_fred()
    end = datetime.now()
    start = end - timedelta(days=days)
    s = fred.get_series(resolved, observation_start=start, observation_end=end)
    rows = []
    for date, val in s.items():
        if val is not None and str(val) != "nan":
            rows.append({"date": date.strftime("%Y-%m-%d"), "value": float(val)})
    return rows


@_ttl_cache(seconds=21600)
def get_macro_overview() -> dict:
    """Return latest values for key macro indicators."""
    targets = {
        "GDP": "GDP",
        "CPI": "CPIAUCSL",
        "Fed_Funds_Rate": "FEDFUNDS",
        "Unemployment": "UNRATE",
        "10Y_Treasury": "DGS10",
        "M2_Money_Supply": "M2SL",
    }
    fred = _get_fred()
    result = {}
    for label, sid in targets.items():
        try:
            s = fred.get_series(sid)
            s = s.dropna()
            if len(s) > 0:
                result[label] = {
                    "value": float(s.iloc[-1]),
                    "date": s.index[-1].strftime("%Y-%m-%d"),
                    "series_id": sid,
                }
        except Exception as e:
            _log.warning("FRED %s failed: %s", sid, e)
            result[label] = {"error": str(e)}
    return result


# ── Equity enhanced fundamentals ──────────────────────────────────────────


def get_equity_profile(symbol: str) -> dict:
    """Company overview: sector, market cap, P/E, P/B, dividend yield, 52w range."""
    t = _get_ticker(symbol)
    info = t.info
    return {
        "symbol": symbol.upper(),
        "name": info.get("longName") or info.get("shortName", ""),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "market_cap": info.get("marketCap"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ps": info.get("priceToSalesTrailing12Months"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "avg_volume": info.get("averageVolume"),
        "description": (info.get("longBusinessSummary") or "")[:500],
    }


def get_equity_ratios(symbol: str) -> dict:
    """Valuation ratios: P/E, P/B, P/S, EV/EBITDA, ROE, ROA."""
    t = _get_ticker(symbol)
    info = t.info
    return {
        "symbol": symbol.upper(),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ps": info.get("priceToSalesTrailing12Months"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "ev_revenue": info.get("enterpriseToRevenue"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "profit_margin": info.get("profitMargins"),
        "operating_margin": info.get("operatingMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
    }


def get_analyst_estimates(symbol: str) -> dict:
    """Analyst consensus: target price, recommendations, EPS estimates."""
    t = _get_ticker(symbol)
    info = t.info
    result: dict[str, Any] = {
        "symbol": symbol.upper(),
        "target_high": info.get("targetHighPrice"),
        "target_low": info.get("targetLowPrice"),
        "target_mean": info.get("targetMeanPrice"),
        "target_median": info.get("targetMedianPrice"),
        "recommendation": info.get("recommendationKey"),
        "recommendation_mean": info.get("recommendationMean"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
    }
    # EPS estimates
    try:
        eps = t.earnings_estimate
        if eps is not None and not eps.empty:
            result["eps_estimates"] = eps.reset_index().to_dict(orient="records")
    except Exception:
        pass
    # Revenue estimates
    try:
        rev = t.revenue_estimate
        if rev is not None and not rev.empty:
            result["revenue_estimates"] = rev.reset_index().to_dict(orient="records")
    except Exception:
        pass
    return result


def get_insider_trading(symbol: str, limit: int = 20) -> list[dict]:
    """Insider trading from FMP API (needs FMP_API_KEY)."""
    key = os.getenv("FMP_API_KEY", "")
    if not key:
        # Fallback: yfinance insider transactions
        try:
            t = _get_ticker(symbol)
            df = t.insider_transactions
            if df is not None and not df.empty:
                _log.info("insider_trading: FMP key not set, using yfinance fallback for %s", symbol)
                rows = df.head(limit).to_dict(orient="records")
                return _sanitize_rows(rows)
        except Exception as exc:
            _log.warning("insider_trading yfinance fallback failed for %s: %s", symbol, exc)
        return []
    url = f"https://financialmodelingprep.com/api/v4/insider-trading?symbol={symbol.upper()}&limit={limit}&apikey={key}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()[:limit]
    except Exception as e:
        _log.warning("FMP insider trading for %s failed: %s", symbol, e)
        return []


def get_institutional_holders(symbol: str) -> list[dict]:
    """Top institutional holders via yfinance."""
    t = _get_ticker(symbol)
    df = t.institutional_holders
    if df is None or df.empty:
        return []
    rows = df.to_dict(orient="records")
    return _sanitize_rows(rows)


# ── Forex ─────────────────────────────────────────────────────────────────


def get_forex_quote(pair: str) -> dict:
    """Real-time forex quote. pair like 'USDCNY', 'EURUSD', 'USDJPY'."""
    ticker_sym = f"{pair.upper()}=X"
    t = _get_ticker(ticker_sym)
    info = t.info
    return {
        "pair": pair.upper(),
        "price": info.get("regularMarketPrice"),
        "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "bid": info.get("bid"),
        "ask": info.get("ask"),
    }


def get_forex_history(pair: str, days: int = 365) -> list[dict]:
    """Historical forex rates."""
    ticker_sym = f"{pair.upper()}=X"
    t = _get_ticker(ticker_sym)
    df = t.history(period=f"{days}d")
    if df is None or df.empty:
        return []
    rows = []
    for idx, row in df.iterrows():
        rows.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 6),
            "high": round(float(row["High"]), 6),
            "low": round(float(row["Low"]), 6),
            "close": round(float(row["Close"]), 6),
        })
    return rows


# ── Options ───────────────────────────────────────────────────────────────


def get_options_chain(symbol: str, expiry: Optional[str] = None) -> dict:
    """Options chain via yfinance. Returns calls + puts for given expiry."""
    t = _get_ticker(symbol)
    expirations = list(t.options)
    if not expirations:
        return {"symbol": symbol.upper(), "expirations": [], "calls": [], "puts": []}

    target_exp = expiry if expiry and expiry in expirations else expirations[0]
    chain = t.option_chain(target_exp)

    def _df_to_list(df):
        if df is None or df.empty:
            return []
        rows = df.to_dict(orient="records")
        return _sanitize_rows(rows)

    return {
        "symbol": symbol.upper(),
        "expiry": target_exp,
        "expirations": expirations[:10],
        "calls": _df_to_list(chain.calls),
        "puts": _df_to_list(chain.puts),
    }


# ── Helpers ───────────────────────────────────────────────────────────────


def _sanitize_rows(rows: list[dict]) -> list[dict]:
    """Convert non-JSON-serializable values (Timestamp, NaN, etc.)."""
    import math
    clean = []
    for row in rows:
        r = {}
        for k, v in row.items():
            if hasattr(v, "strftime"):
                r[k] = v.strftime("%Y-%m-%d")
            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r[k] = None
            else:
                r[k] = v
        clean.append(r)
    return clean
