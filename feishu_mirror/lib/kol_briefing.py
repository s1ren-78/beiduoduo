"""KOL 观点日报 — 搜索、抓取、摘要、组装飞书卡片。"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "kol_config.json"

# ── Data types ──


@dataclass
class KolConfig:
    id: str
    name: str
    title: str
    search_queries: list[str]
    category: str  # "crypto" | "tech"
    enabled: bool = True


@dataclass
class KolArticle:
    url: str
    title: str
    snippet: str  # search snippet (fallback)
    content: str = ""  # scraped full text
    source_type: str = "web"  # "web" | "youtube"


@dataclass
class KolSummary:
    kol: KolConfig
    points: list[str] = field(default_factory=list)  # 核心观点
    sources: list[str] = field(default_factory=list)  # source URLs
    source_types: list[str] = field(default_factory=list)  # "web" | "youtube"
    error: str | None = None


# ── Config ──


def load_kol_config() -> tuple[list[KolConfig], dict]:
    """Load KOL list + settings from JSON config."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    kols = []
    for k in raw.get("kols", []):
        if not k.get("enabled", True):
            continue
        kols.append(KolConfig(
            id=k["id"],
            name=k["name"],
            title=k.get("title", ""),
            search_queries=k.get("search_queries", [k["name"]]),
            category=k.get("category", ""),
        ))

    settings = raw.get("settings", {})
    return kols, settings


# ── Search + Scrape ──


def _search_with_retry(searcher, query: str, count: int) -> dict:
    """Search with 24h → weekly fallback + retry on error."""
    import time
    result = searcher.search(query, count=count, freshness="pd")
    if not result.get("results") and not result.get("error"):
        result = searcher.search(query, count=count, freshness="pw")
    if result.get("error"):
        time.sleep(2)
        result = searcher.search(query, count=count, freshness="pw")
    return result


# Sites to auto-search per KOL (query appended with site: filter)
_AUTO_SEARCH_SITES = ["youtube.com"]


def fetch_kol_articles(
    kol: KolConfig,
    searcher,
    settings: dict,
) -> list[KolArticle]:
    """Search DuckDuckGo + YouTube + scrape top articles for one KOL."""
    from lib.web_reader import fetch_page

    max_results = settings.get("max_search_results_per_query", 5)
    max_scrape = settings.get("max_scrape_per_person", 3)
    max_chars = settings.get("scrape_max_chars", 6000)

    seen_urls: set[str] = set()
    articles: list[KolArticle] = []

    # 1. Normal web search
    for query in kol.search_queries:
        result = _search_with_retry(searcher, query, max_results)
        for item in result.get("results", []):
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            articles.append(KolArticle(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("description", ""),
            ))

    # 2. Auto site-specific search (YouTube, etc.)
    for site in _AUTO_SEARCH_SITES:
        site_query = f"{kol.name} site:{site}"
        result = _search_with_retry(searcher, site_query, 3)
        for item in result.get("results", []):
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            articles.append(KolArticle(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("description", ""),
                source_type="youtube" if "youtube.com" in url else "web",
            ))

    # Scrape top N articles (skip YouTube — Playwright can't extract video content)
    scraped = 0
    for article in articles:
        if scraped >= max_scrape:
            break
        if article.source_type == "youtube":
            continue  # YouTube snippet is enough for Claude
        try:
            page = fetch_page(article.url, max_chars=max_chars)
            article.content = page.get("content", "")
            scraped += 1
        except Exception as e:
            logger.warning("Scrape failed for %s: %s", article.url, e)

    return articles


# ── Claude summarization ──


def _build_prompt(kol: KolConfig, articles: list[KolArticle]) -> str:
    """Build Claude prompt for extracting KOL opinions."""
    texts = []
    for i, a in enumerate(articles, 1):
        body = a.content.strip() if a.content.strip() else a.snippet
        texts.append(f"[文章{i}] {a.title}\n{body[:4000]}")

    joined = "\n\n---\n\n".join(texts)
    return (
        f"以下是可能与 {kol.name}（{kol.title}）相关的近期新闻。\n\n"
        f"{joined}\n\n"
        f"任务：提炼 {kol.name} 本人近期的 2-3 条核心观点或重要动态。\n\n"
        f"严格规则：\n"
        f"1. 只输出 bullet point，每行以「• 」开头，每条不超过 40 字\n"
        f"2. 只提取 {kol.name} 本人的言论、决策或直接相关的重大事件\n"
        f"3. 与此人无关的文章直接忽略，不要解释为什么忽略\n"
        f"4. 如果所有文章都与 {kol.name} 无关，只输出：暂无新动态\n"
        f"5. 禁止输出任何解释、说明、前缀语。只有 bullet point 或「暂无新动态」\n\n"
        f"用中文输出。"
    )


def summarize_kol_opinions(
    kol: KolConfig,
    articles: list[KolArticle],
    settings: dict,
) -> KolSummary:
    """Use Claude Haiku to distill core opinions."""
    summary = KolSummary(
        kol=kol,
        sources=[a.url for a in articles[:5] if a.url],
        source_types=[a.source_type for a in articles[:5] if a.url],
    )

    if not articles:
        summary.points = ["暂无新动态"]
        return summary

    # Build text for Claude
    prompt = _build_prompt(kol, articles)
    model = settings.get("claude_model", "claude-haiku-4-5-20251001")

    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()

        # Check for "no updates" response
        if "暂无新动态" in text and len(text) < 20:
            summary.points = ["暂无新动态"]
            return summary

        # Parse bullet points only — ignore non-bullet lines
        points = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Only accept lines starting with bullet markers
            is_bullet = False
            for prefix in ("• ", "· ", "- ", "* ", "•", "·"):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    is_bullet = True
                    break
            if is_bullet and line and "暂无" not in line:
                points.append(line)

        summary.points = points[:settings.get("summary_max_points", 3)] if points else ["暂无新动态"]

    except Exception as e:
        logger.error("Claude summarization failed for %s: %s", kol.name, e)
        summary.error = str(e)
        # Fallback: use raw snippets
        summary.points = [
            a.snippet[:80] for a in articles[:2] if a.snippet
        ] or ["暂无新动态"]

    return summary


# ── Orchestrator ──


def fetch_all_kol_summaries(
    kols: list[KolConfig],
    settings: dict,
) -> list[KolSummary]:
    """Fetch articles + summarize for all KOLs, sequentially."""
    from lib.web_search import WebSearchClient

    searcher = WebSearchClient()
    summaries: list[KolSummary] = []

    for kol in kols:
        logger.info("Processing KOL: %s", kol.name)
        try:
            articles = fetch_kol_articles(kol, searcher, settings)
            logger.info("  Found %d articles", len(articles))
            summary = summarize_kol_opinions(kol, articles, settings)
        except Exception as e:
            logger.error("KOL pipeline failed for %s: %s", kol.name, e)
            summary = KolSummary(kol=kol, points=["处理失败"], error=str(e))
        summaries.append(summary)

    return summaries


# ── Feishu Card Builder (Schema 2.0) ──

_CATEGORY_META = {
    "crypto": {"label": "Crypto", "icon": "🪙", "color": "orange"},
    "tech":   {"label": "Tech",   "icon": "💻", "color": "blue"},
}


def _kol_block(summary: KolSummary) -> list[dict]:
    """Build elements for one KOL — a visually distinct block."""
    kol = summary.kol
    meta = _CATEGORY_META.get(kol.category, {"label": "", "icon": "👤", "color": "grey"})
    has_content = summary.points and summary.points != ["暂无新动态"]

    # Name row: icon + name + title tag
    name_line = f"**{kol.name}**　<font color='{meta['color']}'>{kol.title}</font>"

    # Points
    if has_content:
        points_lines = []
        for p in summary.points:
            points_lines.append(f"◦ {p}")
        points_md = "\n".join(points_lines)
    else:
        points_md = "<font color='grey'>— 暂无新动态 —</font>"

    # Source links (inline, subtle, with type icons)
    if has_content and summary.sources:
        link_parts = []
        types = summary.source_types or ["web"] * len(summary.sources)
        for i, (u, t) in enumerate(zip(summary.sources[:3], types[:3]), 1):
            icon = "▶" if t == "youtube" else str(i)
            link_parts.append(f"[{icon}]({u})")
        points_md += f"\n<font color='grey'>📎 {' · '.join(link_parts)}</font>"

    return [
        {"tag": "markdown", "content": name_line},
        {"tag": "markdown", "content": points_md},
    ]


def build_kol_card(summaries: list[KolSummary], date_str: str) -> dict:
    """Assemble Feishu Schema 2.0 card."""
    elements: list[dict] = []

    # Group by category
    groups: dict[str, list[KolSummary]] = {}
    for s in summaries:
        groups.setdefault(s.kol.category, []).append(s)

    # Render order: crypto → tech → other
    order = ["crypto", "tech"]
    ordered_keys = [k for k in order if k in groups] + [k for k in groups if k not in order]

    for idx, cat in enumerate(ordered_keys):
        group = groups[cat]
        meta = _CATEGORY_META.get(cat, {"label": cat.title(), "icon": "📡", "color": "grey"})

        if idx > 0:
            elements.append({"tag": "hr"})

        # Category header
        elements.append({
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "default",
            "columns": [{
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [{
                    "tag": "markdown",
                    "content": f"{meta['icon']}  **{meta['label']}**",
                }],
            }],
        })

        # Each KOL in this category
        for i, summary in enumerate(group):
            elements.extend(_kol_block(summary))
            # Light separator between KOLs in same category (not after last)
            if i < len(group) - 1:
                elements.append({"tag": "markdown", "content": " "})

    # Footer
    active_count = sum(
        1 for s in summaries
        if s.points and s.points != ["暂无新动态"]
    )
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "markdown",
        "content": (
            f"<font color='grey'>"
            f"{date_str}　·　{active_count}/{len(summaries)} 位有新动态　·　贝多多"
            f"</font>"
        ),
    })

    return {
        "schema": "2.0",
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"🎯 KOL 观点速递 · {date_str}",
            },
            "subtitle": {
                "tag": "plain_text",
                "content": "Daily KOL Briefing · 贝多多",
            },
            "template": "violet",
        },
        "body": {
            "elements": elements,
        },
    }
