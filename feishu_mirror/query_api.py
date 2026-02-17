from __future__ import annotations

import base64
import json as _json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from lib.config import ensure_runtime_dirs, load_settings
from lib.db import DB
from lib.db_market import (
    get_quote_latest,
    get_watchlist,
    query_chain_daily,
    query_fin_statement,
    query_price_daily,
    query_protocol_daily,
    query_token_liquidity,
    upsert_fin_statement,
    upsert_price_daily,
    upsert_protocol_daily,
    upsert_chain_daily,
    upsert_quote_latest,
    upsert_watchlist,
)
from lib.db_structured import (
    get_report_structured,
    query_enriched_reports,
    query_metrics,
    query_theses,
    structurize_stats,
)
from lib.jobs import (
    ensure_schema,
    run_all_sync,
    run_feishu_sync,
    run_financials_sync,
    run_local_sync,
    run_market_sync,
)
from lib.web_search import WebSearchClient
from lib.web_reader import fetch_page
from lib.chart_render import render_bar_chart, render_line_chart, render_multi_line_chart, render_tradingview_screenshot
from lib.feishu_api import FeishuAuth, FeishuClient
from lib.feishu_bitable import FeishuBitableClient
from lib.market_api import ArtemisClient, YFinanceClient
from lib.sec_api import SECEdgarClient
from lib.openbb_api import (
    get_macro_indicator,
    get_macro_overview,
    get_equity_profile,
    get_equity_ratios,
    get_analyst_estimates,
    get_insider_trading,
    get_institutional_holders,
    get_forex_quote,
    get_forex_history,
    get_options_chain,
)


class SyncRunRequest(BaseModel):
    scope: str = Field(pattern="^(local|feishu|all|market|financials)$")
    mode: str = Field(pattern="^(full|incremental)$")
    reason: str = Field(pattern="^(manual|schedule|miss)$")


class WatchlistRequest(BaseModel):
    symbol: str = Field(min_length=1)
    asset_class: str = Field(pattern="^(stock|crypto|protocol|chain)$")
    label: Optional[str] = None
    enabled: bool = True
    meta: Optional[dict] = None


class ChartRenderRequest(BaseModel):
    chart_type: str = Field(pattern="^(line|multi_line|bar|candlestick)$")
    title: str = Field(min_length=1)
    data: Any = None  # list[dict] for line/bar, list[{label, data}] for multi_line; optional for candlestick with symbol
    y_label: str = ""
    symbol: Optional[str] = None           # e.g. "GOOGL", "AAVE" — used for TradingView screenshot
    asset_class: Optional[str] = None      # "stock" | "crypto" — used for TradingView screenshot
    chat_id: Optional[str] = None          # group chat id (oc_xxx)
    open_id: Optional[str] = None          # user open_id for DM (ou_xxx)
    receive_id: Optional[str] = None       # generic receive_id
    receive_id_type: str = "chat_id"       # chat_id | open_id


class BitableCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    fields: list[dict]
    records: list[dict]
    folder_token: str = ""


settings = load_settings(str(Path(__file__).parent / ".env"))
ensure_runtime_dirs(settings)
db = DB(settings.database_url)
ensure_schema(db, Path(__file__).parent / "schema.sql")

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
app = FastAPI(title="Beiduoduo Report Query API", version="1.0.0")
_log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_yf() -> YFinanceClient:
    return YFinanceClient()


@lru_cache(maxsize=1)
def _get_artemis() -> ArtemisClient:
    return ArtemisClient(settings.artemis_api_key)


@lru_cache(maxsize=1)
def _get_sec() -> SECEdgarClient:
    return SECEdgarClient(settings.sec_edgar_user_agent)


@lru_cache(maxsize=1)
def _get_feishu() -> FeishuClient:
    return FeishuClient(FeishuAuth(app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret))


@lru_cache(maxsize=1)
def _get_web_search() -> WebSearchClient:
    return WebSearchClient()


def _cache_write(fn) -> None:
    """Non-fatal write-through cache call. fn is a zero-arg callable."""
    try:
        fn()
    except Exception as exc:
        _log.warning("cache write failed: %s", exc)


def _send_feishu_image(png: bytes, rid: str, rid_type: str, result: dict[str, Any]) -> None:
    """Upload PNG to Feishu and send to rid. Mutates result dict."""
    try:
        client = _get_feishu()
        image_key = client.upload_image(png)
        resp = client.send_image_as_card(rid, image_key, receive_id_type=rid_type)
        result["image_key"] = image_key
        result["sent_to"] = rid
        msg_id = resp.get("message_id", "") if isinstance(resp, dict) else ""
        result["message_id"] = msg_id
        _log.info("Feishu image sent OK: image_key=%s, rid=%s, message_id=%s", image_key, rid, msg_id)
    except Exception as exc:
        _log.warning("Feishu image send failed: %s", exc)
        result["send_error"] = str(exc)


@app.get("/health")
def health() -> dict:
    return {"ok": "true"}


@app.get("/v1/search")
def search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(settings.default_top_k, ge=1, le=50),
    source: Optional[str] = Query(default=None, pattern="^(local|feishu)$"),
    tag: Optional[str] = None,
    from_ts: Optional[datetime] = Query(default=None, alias="from"),
    to_ts: Optional[datetime] = Query(default=None, alias="to"),
):
    if from_ts and to_ts and from_ts >= to_ts:
        raise HTTPException(status_code=400, detail="'from' must be before 'to'")
    rows = db.search(
        query=q,
        top_k=top_k,
        source=source,
        tag=tag,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return {
        "query": q,
        "top_k": top_k,
        "hits": [
            {
                "doc_id": row.doc_id,
                "title": row.title,
                "source_type": row.source_type,
                "category": row.category,
                "chunk_id": row.chunk_id,
                "score": row.score,
                "quote": row.quote,
                "start_offset": row.start_offset,
                "end_offset": row.end_offset,
                "file_path": row.file_path,
                "updated_at": row.updated_at,
            }
            for row in rows
        ],
    }


@app.get("/v1/docs/{doc_id}")
def get_doc(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="doc not found")

    chunks = doc.pop("chunks", [])
    sections = [
        {
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "section": chunk.get("section"),
            "start_offset": chunk["start_offset"],
            "end_offset": chunk["end_offset"],
        }
        for chunk in chunks
    ]
    citations = [
        {
            "doc_id": doc["doc_id"],
            "chunk_id": chunk["chunk_id"],
            "quote": chunk["content"],
            "start_offset": chunk["start_offset"],
            "end_offset": chunk["end_offset"],
        }
        for chunk in chunks
    ]

    return {
        "meta": doc,
        "full_text": doc.get("full_text", ""),
        "sections": sections,
        "citations": citations,
    }


@app.post("/v1/sync/run")
def run_sync(payload: SyncRunRequest, background_tasks: BackgroundTasks):
    run_id = db.start_sync_run(payload.scope, payload.mode, payload.reason)

    def _runner() -> None:
        try:
            if payload.scope == "local":
                result = run_local_sync(
                    db, settings, mode=payload.mode, reason=payload.reason, run_id=run_id
                )
            elif payload.scope == "feishu":
                result = run_feishu_sync(
                    db, settings, mode=payload.mode, reason=payload.reason, run_id=run_id
                )
            elif payload.scope == "market":
                result = run_market_sync(
                    db, settings, mode=payload.mode, reason=payload.reason, run_id=run_id
                )
            elif payload.scope == "financials":
                result = run_financials_sync(
                    db, settings, mode=payload.mode, reason=payload.reason, run_id=run_id
                )
            else:
                result = run_all_sync(
                    db, settings, mode=payload.mode, reason=payload.reason, run_id=run_id
                )
            db.finish_sync_run(run_id, "success", result.get("stats", {}), None)
        except Exception as exc:
            db.finish_sync_run(run_id, "failed", {}, str(exc))

    db.finish_sync_run(run_id, "running", {"queued": True}, None)
    background_tasks.add_task(_runner)
    return {"run_id": run_id, "status": "queued"}


@app.get("/v1/sync/status")
def sync_status():
    status = db.sync_status()
    status["recent_runs"] = db.recent_sync_runs(20)
    return status


# ── Market & On-chain Endpoints (real-time with write-through cache) ──


@app.get("/v1/market/quote")
def market_quote(
    symbol: str = Query(..., min_length=1),
    asset_class: str = Query(..., pattern="^(stock|crypto)$"),
):
    """Real-time quote: calls yfinance (stock) or Artemis (crypto), caches to DB."""
    quote = None
    if asset_class == "stock":
        quote = _get_yf().get_quote(symbol)
    else:
        quote = _get_artemis().get_crypto_quote(symbol)

    if not quote:
        raise HTTPException(status_code=404, detail=f"quote not found for {symbol}")

    _cache_write(lambda: upsert_quote_latest(
        db, quote["symbol"], asset_class,
        quote.get("price"), quote.get("change_pct"),
        quote.get("volume"), quote.get("market_cap"),
        meta=quote.get("meta"),
    ))
    return quote


@app.get("/v1/market/history")
def market_history(
    symbol: str = Query(..., min_length=1),
    asset_class: str = Query(..., pattern="^(stock|crypto)$"),
    days: int = Query(30, ge=1, le=3650),
    chart: bool = Query(True, description="Auto-render candlestick chart"),
    chat_id: Optional[str] = Query(None, description="Feishu chat_id to auto-send chart"),
    open_id: Optional[str] = Query(None, description="Feishu open_id to auto-send chart"),
):
    """Real-time history: calls yfinance (stock) or Artemis (crypto), caches to DB."""
    if asset_class == "stock":
        rows = _get_yf().get_history(symbol, days=days)
    else:
        rows = _get_artemis().get_crypto_history(symbol, days=days)

    _cache_write(lambda: upsert_price_daily(db, rows))

    result: dict[str, Any] = {"symbol": symbol.upper(), "asset_class": asset_class, "days": days, "data": rows}

    if chart and rows:
        try:
            png = render_tradingview_screenshot(symbol, asset_class)
            result["chart_base64"] = base64.b64encode(png).decode()
            rid = chat_id or open_id
            if rid:
                _send_feishu_image(png, rid, "chat_id" if chat_id else "open_id", result)
        except Exception as exc:
            _log.warning("TradingView screenshot failed for %s: %s", symbol, exc)
            result["chart_error"] = f"截图失败: {exc}"

    return result


@app.get("/v1/financials")
def financials(
    entity_id: str = Query(..., min_length=1),
    entity_type: str = Query(..., pattern="^(stock|protocol)$"),
    limit: int = Query(8, ge=1, le=200),
):
    """Real-time financials: calls SEC EDGAR (stock) or Artemis (protocol)."""
    if entity_type == "stock":
        rows = _get_sec().get_financials(entity_id)
    else:
        rows = _get_artemis().get_protocol_financials(entity_id)

    _cache_write(lambda: upsert_fin_statement(db, rows))

    # Apply limit (most recent first)
    rows.sort(key=lambda r: r.get("period", ""), reverse=True)
    rows = rows[:limit]
    return {"entity_id": entity_id.upper(), "entity_type": entity_type, "data": rows}


@app.get("/v1/onchain/protocol")
def onchain_protocol(
    protocol: str = Query(..., min_length=1),
    days: int = Query(30, ge=1, le=3650),
):
    """Real-time protocol metrics from Artemis (TVL, revenue, fees)."""
    rows = _get_artemis().get_protocol_metrics(protocol, days=days)
    _cache_write(lambda: upsert_protocol_daily(db, rows))
    return {"protocol": protocol.lower(), "days": days, "data": rows}


@app.get("/v1/onchain/chain")
def onchain_chain(
    chain: str = Query(..., min_length=1),
    days: int = Query(30, ge=1, le=3650),
):
    """Real-time chain metrics from Artemis (txns, TVL)."""
    rows = _get_artemis().get_chain_metrics(chain, days=days)
    _cache_write(lambda: upsert_chain_daily(db, rows))
    return {"chain": chain.lower(), "days": days, "data": rows}


@app.get("/v1/onchain/liquidity")
def onchain_liquidity(
    token: str = Query(..., min_length=1),
    chain: str = Query(..., min_length=1),
    days: int = Query(30, ge=1, le=3650),
):
    """Token liquidity — currently not available via Artemis SDK."""
    rows = _get_artemis().get_token_liquidity(token, chain, days=days)
    return {"token": token.upper(), "chain": chain.lower(), "days": days, "data": rows}


@app.get("/v1/web/search")
def web_search(
    q: str = Query(..., min_length=1),
    count: int = Query(10, ge=1, le=20),
    offset: int = Query(0, ge=0, le=9),
    freshness: Optional[str] = Query(default=None, pattern="^(pd|pw|pm|py)$"),
    country: Optional[str] = Query(default=None, min_length=2, max_length=2),
    search_lang: Optional[str] = Query(default=None, min_length=2, max_length=5),
):
    """Web search via DuckDuckGo (free, no API key)."""
    return _get_web_search().search(
        q=q, count=count,
        freshness=freshness, country=country, search_lang=search_lang,
    )


@app.get("/v1/web/read")
def web_read(
    url: str = Query(..., min_length=1),
    max_chars: int = Query(8000, ge=1000, le=30000),
):
    """Fetch a web page and extract text content using Playwright."""
    return fetch_page(url, max_chars=max_chars)


@app.get("/v1/watchlist")
def watchlist_get(
    asset_class: Optional[str] = Query(default=None, pattern="^(stock|crypto|protocol|chain)$"),
):
    rows = get_watchlist(db, asset_class=asset_class, enabled_only=False)
    return {"data": rows}


@app.post("/v1/watchlist")
def watchlist_post(payload: WatchlistRequest):
    wid = upsert_watchlist(
        db,
        symbol=payload.symbol,
        asset_class=payload.asset_class,
        label=payload.label,
        enabled=payload.enabled,
        meta=payload.meta,
    )
    return {"id": wid, "symbol": payload.symbol.upper(), "asset_class": payload.asset_class}


# ── Chart & Bitable Endpoints ──


@app.post("/v1/chart/render")
def chart_render(payload: ChartRenderRequest):
    """Render chart to PNG. Optionally upload to Feishu and send to chat."""
    data = payload.data
    if isinstance(data, str):
        data = _json.loads(data)

    # Route 1: symbol provided → TradingView screenshot (唯一路径，不 fallback)
    if payload.symbol:
        png = render_tradingview_screenshot(payload.symbol, payload.asset_class or "stock")
    else:
        # Route 2: no symbol → local rendering for non-price charts only
        if payload.chart_type == "candlestick":
            raise HTTPException(
                status_code=400,
                detail="candlestick chart requires 'symbol' (uses TradingView screenshot)",
            )
        if not data:
            raise HTTPException(
                status_code=400,
                detail=f"chart_type={payload.chart_type} requires 'data'",
            )
        if payload.chart_type == "line":
            png = render_line_chart(data, payload.title, y_label=payload.y_label)
        elif payload.chart_type == "multi_line":
            png = render_multi_line_chart(data, payload.title, y_label=payload.y_label)
        elif payload.chart_type == "bar":
            png = render_bar_chart(data, payload.title, y_label=payload.y_label)
        else:
            raise HTTPException(status_code=400, detail=f"unknown chart_type: {payload.chart_type}")

    result: dict[str, Any] = {"image_base64": base64.b64encode(png).decode()}

    # Resolve receive target: chat_id (group) or open_id (DM) or generic receive_id
    rid = payload.receive_id or payload.chat_id or payload.open_id
    rid_type = payload.receive_id_type
    if payload.chat_id and not payload.receive_id:
        rid_type = "chat_id"
    elif payload.open_id and not payload.receive_id:
        rid_type = "open_id"

    if rid:
        _send_feishu_image(png, rid, rid_type, result)

    return result


@app.post("/v1/bitable/create")
def bitable_create(payload: BitableCreateRequest):
    """Create a Feishu Bitable with fields and records."""
    client = _get_feishu()
    bitable = FeishuBitableClient(client)

    # Create app
    app_info = bitable.create_app(payload.name, folder_token=payload.folder_token)
    app_token = app_info["app_token"]

    # Add table with fields
    table_info = bitable.add_table(app_token, payload.name, payload.fields)
    table_id = table_info.get("table_id", "")

    # Batch insert records
    records_created = 0
    if payload.records:
        batch_result = bitable.batch_create_records(app_token, table_id, payload.records)
        records_created = len(batch_result.get("records", []))

    url = app_info.get("url", f"https://feishu.cn/base/{app_token}")
    return {
        "app_token": app_token,
        "table_id": table_id,
        "url": url,
        "records_created": records_created,
    }


# ── Structured Report Endpoints ──


@app.get("/v1/reports/structured")
def reports_structured(
    company: Optional[str] = None,
    sector: Optional[str] = None,
    report_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """List enriched reports filtered by company/sector/type."""
    rows = query_enriched_reports(db, company=company, sector=sector, report_type=report_type, limit=limit)
    return {"data": rows, "count": len(rows)}


@app.get("/v1/reports/{doc_id}/structured")
def report_structured(doc_id: str):
    """Full structured data for a single report."""
    result = get_report_structured(db, doc_id)
    if not result:
        raise HTTPException(status_code=404, detail="structured data not found for this doc_id")
    return result


@app.get("/v1/theses")
def theses(
    company: Optional[str] = None,
    direction: Optional[str] = Query(default=None, pattern="^(bullish|bearish|neutral)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """Cross-report investment thesis query."""
    rows = query_theses(db, company=company, direction=direction, limit=limit)
    return {"data": rows, "count": len(rows)}


@app.get("/v1/metrics")
def metrics(
    company: Optional[str] = None,
    ticker: Optional[str] = None,
    metric: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    """Cross-report financial metrics query."""
    rows = query_metrics(db, company=company, ticker=ticker, metric=metric, limit=limit)
    return {"data": rows, "count": len(rows)}


@app.get("/v1/reports/stats")
def reports_stats():
    """Structurization progress stats."""
    return structurize_stats(db)


# ── OpenBB Data Endpoints (macro, equity enhanced, forex, options) ──


@app.get("/v1/macro/indicator")
def macro_indicator(
    series_id: str = Query(..., min_length=1),
    days: int = Query(365, ge=1, le=7300),
):
    """Single FRED macro indicator (GDP, CPI, FEDFUNDS, UNRATE, DGS10, M2SL)."""
    try:
        rows = get_macro_indicator(series_id, days=days)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rows:
        raise HTTPException(status_code=404, detail=f"no data for series {series_id}")
    return {"series_id": series_id, "days": days, "data": rows}


@app.get("/v1/macro/overview")
def macro_overview():
    """Key US macro indicators at a glance (GDP, CPI, Fed rate, unemployment, 10Y, M2)."""
    try:
        data = get_macro_overview()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


@app.get("/v1/equity/profile")
def equity_profile(symbol: str = Query(..., min_length=1)):
    """Company overview: sector, market cap, P/E, dividend yield, 52-week range."""
    data = get_equity_profile(symbol)
    if not data.get("price"):
        raise HTTPException(status_code=404, detail=f"profile not found for {symbol}")
    return data


@app.get("/v1/equity/ratios")
def equity_ratios(symbol: str = Query(..., min_length=1)):
    """Valuation ratios: P/E, P/B, P/S, EV/EBITDA, ROE, ROA."""
    return get_equity_ratios(symbol)


@app.get("/v1/equity/analysts")
def equity_analysts(symbol: str = Query(..., min_length=1)):
    """Analyst consensus: target price, rating, EPS estimates."""
    return get_analyst_estimates(symbol)


@app.get("/v1/equity/insiders")
def equity_insiders(
    symbol: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Insider trading activity (FMP or yfinance fallback)."""
    return {"symbol": symbol.upper(), "data": get_insider_trading(symbol, limit=limit)}


@app.get("/v1/equity/institutions")
def equity_institutions(symbol: str = Query(..., min_length=1)):
    """Top institutional holders."""
    return {"symbol": symbol.upper(), "data": get_institutional_holders(symbol)}


@app.get("/v1/forex/quote")
def forex_quote(pair: str = Query(..., min_length=3)):
    """Real-time forex rate (USDCNY, EURUSD, USDJPY, etc.)."""
    data = get_forex_quote(pair)
    if not data.get("price"):
        raise HTTPException(status_code=404, detail=f"forex quote not found for {pair}")
    return data


@app.get("/v1/forex/history")
def forex_history(
    pair: str = Query(..., min_length=3),
    days: int = Query(365, ge=1, le=3650),
):
    """Historical forex rates."""
    rows = get_forex_history(pair, days=days)
    if not rows:
        raise HTTPException(status_code=404, detail=f"forex history not found for {pair}")
    return {"pair": pair.upper(), "days": days, "data": rows}


@app.get("/v1/options/chain")
def options_chain(
    symbol: str = Query(..., min_length=1),
    expiry: Optional[str] = Query(None),
):
    """Options chain: strikes, calls, puts, IV, Greeks, OI."""
    data = get_options_chain(symbol, expiry=expiry)
    if not data.get("expirations"):
        raise HTTPException(status_code=404, detail=f"no options found for {symbol}")
    return data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.query_api_host, port=settings.query_api_port)
