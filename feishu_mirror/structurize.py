#!/usr/bin/env python3
"""
研报结构化提取 — 用 Claude 把研报提取为三层结构化数据。

用法:
    python3 structurize.py --layer all              # 跑全部 3 层
    python3 structurize.py --layer 1 --dry-run      # 只输出 JSON，不写库
    python3 structurize.py --layer 2 --limit 5      # 论点提取，只跑 5 篇
    python3 structurize.py --doc-id xxx --layer 3   # 单篇调试
    python3 structurize.py --layer all --force       # 忽略进度，全部重跑
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Add parent dir to path so we can import lib.*
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import load_settings
from lib.db import DB
from lib.db_structured import upsert_metadata, upsert_theses, upsert_metrics

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 200

# Claude models
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-5-20250929"

LAYER_MODELS = {1: MODEL_HAIKU, 2: MODEL_SONNET, 3: MODEL_HAIKU}


# ── Text truncation ──


def truncate_for_context(full_text: str, max_chars: int) -> str:
    """Smart truncation: 70% from start + 30% from end."""
    if len(full_text) <= max_chars:
        return full_text
    head_size = int(max_chars * 0.7)
    tail_size = max_chars - head_size
    return full_text[:head_size] + "\n\n[...truncated...]\n\n" + full_text[-tail_size:]


# ── Document selection ──


def get_unprocessed_docs(
    db: DB, layer: int, limit: int | None = None, force: bool = False, doc_id: str | None = None
) -> list[dict[str, Any]]:
    """Find documents that haven't been processed for a given layer."""
    with db.conn() as conn:
        if doc_id:
            rows = conn.execute(
                "SELECT doc_id, title, category, full_text FROM report_document WHERE doc_id = ?",
                (doc_id,),
            ).fetchall()
            return [r for r in rows if len(r.get("full_text", "")) >= MIN_TEXT_LENGTH]

        if force:
            sql = "SELECT doc_id, title, category, full_text FROM report_document WHERE length(full_text) >= ?"
            params: list[Any] = [MIN_TEXT_LENGTH]
        else:
            table_map = {1: "report_meta_enriched", 2: "report_thesis", 3: "report_metric"}
            target_table = table_map[layer]
            sql = f"""
                SELECT d.doc_id, d.title, d.category, d.full_text
                FROM report_document d
                LEFT JOIN {target_table} e ON e.doc_id = d.doc_id
                WHERE length(d.full_text) >= ? AND e.doc_id IS NULL
            """
            params = [MIN_TEXT_LENGTH]

        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        return conn.execute(sql, params).fetchall()


# ── Claude prompts ──


def _parse_json(text: str) -> Any:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last ``` lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _call_claude(client, model: str, prompt: str, max_tokens: int = 4096) -> str:
    """Call Claude with exponential backoff on rate limits."""
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            err_str = str(e)
            if "rate" in err_str.lower() or "529" in err_str or "overloaded" in err_str.lower():
                wait = 2 ** attempt
                logger.warning("Rate limited, waiting %ds (attempt %d/4): %s", wait, attempt + 1, e)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("Claude API failed after 4 attempts")


def _call_claude_json(client, model: str, prompt: str, max_tokens: int = 4096) -> Any:
    """Call Claude and parse JSON response with one retry on parse failure."""
    text = _call_claude(client, model, prompt, max_tokens)
    try:
        return _parse_json(text)
    except json.JSONDecodeError:
        # Retry once, asking to fix JSON
        retry_prompt = (
            f"Your previous response was not valid JSON. Here it is:\n\n{text}\n\n"
            f"Please output ONLY valid JSON (no markdown, no explanation)."
        )
        text2 = _call_claude(client, model, retry_prompt, max_tokens)
        return _parse_json(text2)


# ── Layer extractors ──


def extract_metadata(doc: dict[str, Any], client, model: str) -> dict[str, Any]:
    """Layer 1: Extract metadata with Haiku."""
    text = truncate_for_context(doc["full_text"], 8000)
    prompt = f"""Analyze this research report and extract metadata as JSON.

REPORT:
{text}

OUTPUT exactly this JSON structure (no explanation, no markdown):
{{
  "display_title": "清晰的报告标题",
  "companies": ["公司名1", "公司名2"],
  "tickers": ["TICKER1", "TICKER2"],
  "sectors": ["赛道1", "赛道2"],
  "report_type": "company_deep_dive|industry_overview|earnings_analysis|thematic|weekly_recap|datapack",
  "language": "zh|en|mixed",
  "publish_date": "YYYY-MM-DD or null",
  "author": "作者名 or null",
  "source_org": "机构名 or null",
  "quality_score": 1-5,
  "summary": "2-3句核心摘要"
}}

Rules:
- report_type must be one of: company_deep_dive, industry_overview, earnings_analysis, thematic, weekly_recap, datapack
- quality_score: 1=raw data dump, 3=decent analysis, 5=top-tier institutional research
- companies/tickers: only include if clearly discussed, not just mentioned in passing
- Output ONLY JSON, nothing else"""
    return _call_claude_json(client, model, prompt)


def extract_theses(doc: dict[str, Any], client, model: str) -> list[dict[str, Any]]:
    """Layer 2: Extract investment theses with Sonnet."""
    text = truncate_for_context(doc["full_text"], 16000)
    prompt = f"""Analyze this research report and extract investment theses as JSON.

REPORT:
{text}

OUTPUT a JSON array of investment theses. Each thesis:
{{
  "company": "公司名",
  "ticker": "TICKER or null",
  "direction": "bullish|bearish|neutral",
  "confidence": "high|medium|low",
  "time_horizon": "short|medium|long",
  "thesis_text": "一段话概括投资论点（50-150字）",
  "key_catalysts": ["催化剂1", "催化剂2"],
  "key_risks": ["风险1", "风险2"]
}}

Rules:
- Only extract theses with clear evidence/reasoning in the report
- Do NOT invent opinions — only extract what is explicitly stated or strongly implied
- One thesis per company (pick the dominant view if multiple exist)
- If no investment thesis exists in the report, return empty array []
- time_horizon: short=<3months, medium=3-12months, long=>1year
- Output ONLY valid JSON array, nothing else"""
    result = _call_claude_json(client, model, prompt)
    if isinstance(result, dict) and "theses" in result:
        result = result["theses"]
    return result if isinstance(result, list) else []


def extract_metrics(doc: dict[str, Any], client, model: str) -> list[dict[str, Any]]:
    """Layer 3: Extract financial metrics with Haiku."""
    text = truncate_for_context(doc["full_text"], 12000)
    prompt = f"""Analyze this research report and extract specific financial numbers/metrics as JSON.

REPORT:
{text}

OUTPUT a JSON array of financial metrics. Each metric:
{{
  "company": "公司名",
  "ticker": "TICKER or null",
  "period": "2024Q3|2024|2024H1|etc",
  "metric": "revenue|net_income|user_count|tvl|trading_volume|etc",
  "value": 12345.67,
  "unit": "USD_M|USD_B|CNY_M|count|percent|etc",
  "yoy_change": 0.15 or null,
  "context": "简短上下文说明"
}}

Rules:
- Only extract CONCRETE numbers explicitly stated in the report
- Do NOT calculate or estimate — only extract what is written
- period format: YYYY for annual, YYYYQ1-4 for quarterly, YYYYH1/H2 for half-year
- value must be numeric (no strings like "约10亿" — convert to 1000 with unit=CNY_M)
- yoy_change as decimal (0.15 = 15% growth, -0.05 = 5% decline)
- Maximum 50 metrics per report
- If no concrete metrics exist, return empty array []
- Output ONLY valid JSON array, nothing else"""
    result = _call_claude_json(client, model, prompt)
    if isinstance(result, dict) and "metrics" in result:
        result = result["metrics"]
    items = result if isinstance(result, list) else []
    return items[:50]


# ── Main processing loop ──


EXTRACTORS = {
    1: extract_metadata,
    2: extract_theses,
    3: extract_metrics,
}

WRITERS = {
    1: lambda db, doc_id, data, model: upsert_metadata(db, doc_id, data, model),
    2: lambda db, doc_id, data, model: upsert_theses(db, doc_id, data, model),
    3: lambda db, doc_id, data, model: upsert_metrics(db, doc_id, data, model),
}


def process_layer(
    db: DB,
    layer: int,
    client,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    doc_id: str | None = None,
) -> dict[str, Any]:
    model = LAYER_MODELS[layer]
    docs = get_unprocessed_docs(db, layer, limit=limit, force=force, doc_id=doc_id)
    logger.info("Layer %d: %d documents to process (model=%s)", layer, len(docs), model)

    stats = {"total": len(docs), "success": 0, "failed": 0, "skipped": 0}
    extractor = EXTRACTORS[layer]
    writer = WRITERS[layer]

    for i, doc in enumerate(docs, 1):
        did = doc["doc_id"]
        title = doc.get("title", "")[:50]
        logger.info("  [%d/%d] %s — %s", i, stats["total"], did[:12], title)

        try:
            result = extractor(doc, client, model)
        except json.JSONDecodeError as e:
            logger.warning("    JSON parse failed, skipping: %s", e)
            stats["failed"] += 1
            continue
        except Exception as e:
            logger.error("    Extraction error, skipping: %s", e)
            stats["failed"] += 1
            continue

        if dry_run:
            print(json.dumps({"doc_id": did, "layer": layer, "result": result}, ensure_ascii=False, indent=2))
            stats["success"] += 1
            continue

        try:
            writer(db, did, result, model)
            stats["success"] += 1
        except Exception as e:
            logger.error("    DB write error: %s", e)
            stats["failed"] += 1

    return stats


# ── CLI ──


def main():
    parser = argparse.ArgumentParser(description="研报结构化提取")
    parser.add_argument("--layer", required=True, help="1, 2, 3, or all")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to process")
    parser.add_argument("--doc-id", default=None, help="Process single document")
    parser.add_argument("--dry-run", action="store_true", help="Output JSON without writing to DB")
    parser.add_argument("--force", action="store_true", help="Re-process already processed documents")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s: %(message)s",
    )

    settings = load_settings(str(Path(__file__).parent / ".env"))
    db = DB(settings.database_url)
    db.ensure_schema(Path(__file__).parent / "schema.sql")

    import anthropic
    client = anthropic.Anthropic()

    layers = [1, 2, 3] if args.layer == "all" else [int(args.layer)]
    all_stats: dict[int, dict] = {}

    for layer in layers:
        logger.info("=== Layer %d ===", layer)
        stats = process_layer(
            db, layer, client,
            limit=args.limit,
            force=args.force,
            dry_run=args.dry_run,
            doc_id=args.doc_id,
        )
        all_stats[layer] = stats
        logger.info("Layer %d done: %s", layer, stats)

    # Print summary to stderr (keep stdout clean for dry-run JSON)
    print("\n" + "=" * 50, file=sys.stderr)
    for layer, stats in all_stats.items():
        print(f"Layer {layer}: {stats['success']}/{stats['total']} success, {stats['failed']} failed", file=sys.stderr)
    print("=" * 50, file=sys.stderr)


if __name__ == "__main__":
    main()
