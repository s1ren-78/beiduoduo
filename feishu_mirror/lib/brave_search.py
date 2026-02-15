"""Brave Search API client."""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class BraveSearchClient:
    """Wraps Brave Search API for web search."""

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
        })

    def search(
        self,
        q: str,
        count: int = 10,
        offset: int = 0,
        freshness: Optional[str] = None,
        country: Optional[str] = None,
        search_lang: Optional[str] = None,
        extra_snippets: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": q,
            "count": min(count, 20),
            "offset": offset,
            "extra_snippets": "true" if extra_snippets else "false",
        }
        if freshness:
            params["freshness"] = freshness
        if country:
            params["country"] = country
        if search_lang:
            params["search_lang"] = search_lang

        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Brave search failed for %r: %s", q, e)
            return {"query": q, "results": [], "error": str(e)}

        web = data.get("web", {})
        results = []
        for item in (web.get("results") or []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "extra_snippets": item.get("extra_snippets", []),
            })

        return {
            "query": q,
            "count": len(results),
            "results": results,
        }
