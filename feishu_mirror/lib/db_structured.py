"""Database operations for structured report enrichment tables."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Layer 1: Metadata ──


def upsert_metadata(db: DB, doc_id: str, data: dict[str, Any], model: str) -> None:
    now = _now_iso()
    with db.conn() as conn:
        conn.execute(
            """
            INSERT INTO report_meta_enriched(
                doc_id, display_title, companies, tickers, sectors,
                report_type, language, publish_date, author, source_org,
                quality_score, summary, model_used, extracted_at, meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                display_title = excluded.display_title,
                companies = excluded.companies,
                tickers = excluded.tickers,
                sectors = excluded.sectors,
                report_type = excluded.report_type,
                language = excluded.language,
                publish_date = excluded.publish_date,
                author = excluded.author,
                source_org = excluded.source_org,
                quality_score = excluded.quality_score,
                summary = excluded.summary,
                model_used = excluded.model_used,
                extracted_at = excluded.extracted_at,
                meta = excluded.meta
            """,
            (
                doc_id,
                data.get("display_title"),
                json.dumps(data.get("companies", []), ensure_ascii=False),
                json.dumps(data.get("tickers", []), ensure_ascii=False),
                json.dumps(data.get("sectors", []), ensure_ascii=False),
                data.get("report_type"),
                data.get("language"),
                data.get("publish_date"),
                data.get("author"),
                data.get("source_org"),
                data.get("quality_score"),
                data.get("summary"),
                model,
                now,
                json.dumps(data.get("meta", {}), ensure_ascii=False),
            ),
        )


# ── Layer 2: Theses ──


def upsert_theses(db: DB, doc_id: str, theses: list[dict[str, Any]], model: str) -> None:
    now = _now_iso()
    with db.conn() as conn:
        conn.execute("DELETE FROM report_thesis WHERE doc_id = ?", (doc_id,))
        for t in theses:
            conn.execute(
                """
                INSERT INTO report_thesis(
                    doc_id, company, ticker, direction, confidence, time_horizon,
                    thesis_text, key_catalysts, key_risks, model_used, extracted_at, meta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    t["company"],
                    t.get("ticker"),
                    t["direction"],
                    t["confidence"],
                    t.get("time_horizon"),
                    t["thesis_text"],
                    json.dumps(t.get("key_catalysts", []), ensure_ascii=False),
                    json.dumps(t.get("key_risks", []), ensure_ascii=False),
                    model,
                    now,
                    json.dumps(t.get("meta", {}), ensure_ascii=False),
                ),
            )


# ── Layer 3: Metrics ──


def upsert_metrics(db: DB, doc_id: str, metrics: list[dict[str, Any]], model: str) -> None:
    now = _now_iso()
    with db.conn() as conn:
        conn.execute("DELETE FROM report_metric WHERE doc_id = ?", (doc_id,))
        for m in metrics:
            conn.execute(
                """
                INSERT INTO report_metric(
                    doc_id, company, ticker, period, metric, value, unit,
                    yoy_change, context, model_used, extracted_at, meta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    m["company"],
                    m.get("ticker"),
                    m["period"],
                    m["metric"],
                    m.get("value"),
                    m.get("unit"),
                    m.get("yoy_change"),
                    m.get("context"),
                    model,
                    now,
                    json.dumps(m.get("meta", {}), ensure_ascii=False),
                ),
            )


# ── Query functions ──


def query_enriched_reports(
    db: DB,
    company: str | None = None,
    sector: str | None = None,
    report_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if company:
        where.append("m.companies LIKE ?")
        params.append(f"%{company}%")
    if sector:
        where.append("m.sectors LIKE ?")
        params.append(f"%{sector}%")
    if report_type:
        where.append("m.report_type = ?")
        params.append(report_type)
    where_clause = (" AND " + " AND ".join(where)) if where else ""
    params.append(limit)
    with db.conn() as conn:
        rows = conn.execute(
            f"""
            SELECT m.*, d.title AS original_title, d.category
            FROM report_meta_enriched m
            JOIN report_document d ON d.doc_id = m.doc_id
            WHERE 1=1 {where_clause}
            ORDER BY m.extracted_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return rows


def get_report_structured(db: DB, doc_id: str) -> dict[str, Any] | None:
    with db.conn() as conn:
        meta = conn.execute(
            "SELECT * FROM report_meta_enriched WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if not meta:
            return None
        theses = conn.execute(
            "SELECT * FROM report_thesis WHERE doc_id = ? ORDER BY id", (doc_id,)
        ).fetchall()
        metrics = conn.execute(
            "SELECT * FROM report_metric WHERE doc_id = ? ORDER BY id", (doc_id,)
        ).fetchall()
    return {"metadata": meta, "theses": theses, "metrics": metrics}


def query_theses(
    db: DB,
    company: str | None = None,
    direction: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if company:
        where.append("t.company LIKE ?")
        params.append(f"%{company}%")
    if direction:
        where.append("t.direction = ?")
        params.append(direction)
    where_clause = (" AND " + " AND ".join(where)) if where else ""
    params.append(limit)
    with db.conn() as conn:
        rows = conn.execute(
            f"""
            SELECT t.*, d.title AS report_title, d.category
            FROM report_thesis t
            JOIN report_document d ON d.doc_id = t.doc_id
            WHERE 1=1 {where_clause}
            ORDER BY t.extracted_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return rows


def query_metrics(
    db: DB,
    company: str | None = None,
    ticker: str | None = None,
    metric: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if company:
        where.append("r.company LIKE ?")
        params.append(f"%{company}%")
    if ticker:
        where.append("r.ticker = ?")
        params.append(ticker.upper())
    if metric:
        where.append("r.metric LIKE ?")
        params.append(f"%{metric}%")
    where_clause = (" AND " + " AND ".join(where)) if where else ""
    params.append(limit)
    with db.conn() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, d.title AS report_title, d.category
            FROM report_metric r
            JOIN report_document d ON d.doc_id = r.doc_id
            WHERE 1=1 {where_clause}
            ORDER BY r.extracted_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return rows


def structurize_stats(db: DB) -> dict[str, Any]:
    with db.conn() as conn:
        total = conn.execute(
            "SELECT count(*) AS n FROM report_document WHERE length(full_text) >= 200"
        ).fetchone()["n"]
        l1 = conn.execute("SELECT count(*) AS n FROM report_meta_enriched").fetchone()["n"]
        l2 = conn.execute("SELECT count(DISTINCT doc_id) AS n FROM report_thesis").fetchone()["n"]
        l3 = conn.execute("SELECT count(DISTINCT doc_id) AS n FROM report_metric").fetchone()["n"]
    return {
        "total_eligible": total,
        "layer1_metadata": l1,
        "layer2_theses": l2,
        "layer3_metrics": l3,
        "layer1_pct": round(l1 / total * 100, 1) if total else 0,
        "layer2_pct": round(l2 / total * 100, 1) if total else 0,
        "layer3_pct": round(l3 / total * 100, 1) if total else 0,
    }
