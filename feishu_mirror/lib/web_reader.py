"""Read web pages using Playwright (headless Chromium).

Runs Playwright in a subprocess to avoid the sync-API-in-asyncio conflict with FastAPI.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Standalone script executed in a subprocess
_FETCH_SCRIPT = r'''
import json, sys, re

_STRIP = re.compile(r"<script[^>]*>[\s\S]*?</script>|<style[^>]*>[\s\S]*?</style>|<[^>]+>")
_NL = re.compile(r"\n{3,}")
_SP = re.compile(r"[ \t]{2,}")

def html_to_text(html):
    t = _STRIP.sub("\n", html)
    for old, new in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&nbsp;"," "),("&quot;",'"')]:
        t = t.replace(old, new)
    return _NL.sub("\n\n", _SP.sub(" ", t)).strip()

url = sys.argv[1]
max_chars = int(sys.argv[2])
timeout_ms = int(sys.argv[3])

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(1500)
    title = page.title() or ""
    html = page.content()
    browser.close()

text = html_to_text(html)
truncated = len(text) > max_chars
text = text[:max_chars]
print(json.dumps({"url": url, "title": title, "content": text, "chars": len(text), "truncated": truncated}, ensure_ascii=False))
'''


def fetch_page(url: str, timeout_ms: int = 15000, max_chars: int = 8000) -> dict[str, Any]:
    """Fetch a URL with Playwright in a subprocess and return extracted text."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _FETCH_SCRIPT, url, str(max_chars), str(timeout_ms)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            err = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown error"
            logger.error("web_reader subprocess failed: %s", err)
            return {"url": url, "title": "", "content": "", "error": err}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"url": url, "title": "", "content": "", "error": "timeout (30s)"}
    except Exception as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return {"url": url, "title": "", "content": "", "error": str(e)}
