"""Web search via DuckDuckGo (free, no API key needed)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from ddgs import DDGS

logger = logging.getLogger(__name__)


class WebSearchClient:
    """Wraps DuckDuckGo search. No API key required."""

    def search(
        self,
        q: str,
        count: int = 10,
        freshness: Optional[str] = None,
        country: Optional[str] = None,
        search_lang: Optional[str] = None,
    ) -> dict[str, Any]:
        # Map Brave-style freshness to DuckDuckGo timelimit
        timelimit = None
        if freshness:
            timelimit_map = {"pd": "d", "pw": "w", "pm": "m", "py": "y"}
            timelimit = timelimit_map.get(freshness)

        region = None
        if country:
            region = f"{country.lower()}-{search_lang or 'en'}"

        try:
            raw = DDGS().text(
                q,
                max_results=min(count, 20),
                timelimit=timelimit,
                region=region or "wt-wt",
            )
        except Exception as e:
            logger.error("DuckDuckGo search failed for %r: %s", q, e)
            return {"query": q, "results": [], "error": str(e)}

        results = []
        for item in raw:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "description": item.get("body", ""),
            })

        return {
            "query": q,
            "count": len(results),
            "results": results,
        }
