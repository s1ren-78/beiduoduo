#!/usr/bin/env python3
"""
贝多多 Query API 冒烟测试
========================
每次改完代码后运行，在推给用户测试之前自动验证所有关键路径。

用法:
    python3 tests/smoke_test.py              # 快速模式（跳过飞书发送）
    python3 tests/smoke_test.py --full       # 完整模式（含飞书发送验证）
    python3 tests/smoke_test.py --restart    # 自动重启 API 再跑测试

退出码: 0=全部通过, 1=有失败
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

BASE_URL = "http://127.0.0.1:8788"
OWNER_OPEN_ID = "ou_ec332c4e35a82229099b7a04b89488ee"
API_DIR = str(Path(__file__).resolve().parent.parent)
LOG_FILE = str(
    Path(__file__).resolve().parent.parent.parent / "数据库" / "_index" / "logs" / "query_api.log"
)

# ── Helpers ─────────────────────────────────────────────────────────────────

_pass = 0
_fail = 0
_skip = 0


def _req(method: str, path: str, body: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    """Send HTTP request, return (status_code, json_body)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"_error": str(e)}


def check(name: str, ok: bool, detail: str = ""):
    global _pass, _fail
    if ok:
        _pass += 1
        print(f"  \033[32mPASS\033[0m  {name}")
    else:
        _fail += 1
        msg = f" — {detail}" if detail else ""
        print(f"  \033[31mFAIL\033[0m  {name}{msg}")


def skip(name: str, reason: str = ""):
    global _skip
    _skip += 1
    msg = f" — {reason}" if reason else ""
    print(f"  \033[33mSKIP\033[0m  {name}{msg}")


def timed(fn):
    """Decorator that prints elapsed time."""
    def wrapper(*a, **kw):
        t0 = time.time()
        result = fn(*a, **kw)
        elapsed = time.time() - t0
        return result, elapsed
    return wrapper


# ── Test Cases ──────────────────────────────────────────────────────────────


def test_health():
    print("\n── Health ──")
    code, body = _req("GET", "/health")
    check("GET /health returns 200", code == 200, f"got {code}")
    check("response has ok=true", body.get("ok") == "true", f"got {body}")


def test_market_quote():
    print("\n── Market Quote ──")
    code, body = _req("GET", "/v1/market/quote?symbol=AAPL&asset_class=stock")
    check("GET /v1/market/quote returns 200", code == 200, f"got {code}")
    check("response has price", body.get("price") is not None, f"keys={list(body.keys())}")


def test_market_history(full: bool = False):
    print("\n── Market History (stock) ──")

    # Without chart (fast, data-only)
    t0 = time.time()
    code, body = _req("GET", "/v1/market/history?symbol=AAPL&asset_class=stock&days=5&chart=false")
    elapsed = time.time() - t0
    check("data-only returns 200", code == 200, f"got {code}")
    check("has data array", isinstance(body.get("data"), list) and len(body["data"]) > 0,
          f"data={type(body.get('data'))}")
    check("data-only < 10s", elapsed < 10, f"took {elapsed:.1f}s")

    # With TradingView chart
    t0 = time.time()
    code, body = _req("GET", "/v1/market/history?symbol=AAPL&asset_class=stock&days=30&chart=true")
    elapsed = time.time() - t0
    check("with chart returns 200", code == 200, f"got {code}")
    check("has chart_base64", "chart_base64" in body, f"keys={list(body.keys())}")
    if "chart_base64" in body:
        kb = len(body["chart_base64"]) // 1024
        check("chart > 10KB", kb > 10, f"chart={kb}KB")
    check("with chart < 20s", elapsed < 20, f"took {elapsed:.1f}s")

    # With Feishu send
    if full:
        t0 = time.time()
        code, body = _req(
            "GET",
            f"/v1/market/history?symbol=GOOGL&asset_class=stock&days=30&chart=true&open_id={OWNER_OPEN_ID}",
        )
        elapsed = time.time() - t0
        check("Feishu send returns 200", code == 200, f"got {code}")
        check("sent_to is set", body.get("sent_to") == OWNER_OPEN_ID,
              f"sent_to={body.get('sent_to')}")
        check("image_key is set", body.get("image_key", "").startswith("img_"),
              f"image_key={body.get('image_key')}")
    else:
        skip("Feishu send (use --full)")


def test_market_history_crypto():
    print("\n── Market History (crypto) ──")
    t0 = time.time()
    code, body = _req("GET", "/v1/market/history?symbol=BTC&asset_class=crypto&days=7&chart=true")
    elapsed = time.time() - t0
    check("crypto returns 200", code == 200, f"got {code}")
    check("has data", isinstance(body.get("data"), list) and len(body["data"]) > 0)
    check("has chart_base64", "chart_base64" in body, f"keys={list(body.keys())}")
    check("crypto < 20s", elapsed < 20, f"took {elapsed:.1f}s")


def test_chart_render_tradingview():
    print("\n── Chart Render (TradingView) ──")
    t0 = time.time()
    code, body = _req("POST", "/v1/chart/render", {
        "chart_type": "candlestick",
        "title": "AAPL K线图",
        "symbol": "AAPL",
        "asset_class": "stock",
    })
    elapsed = time.time() - t0
    check("TradingView chart returns 200", code == 200, f"got {code}: {body.get('detail', '')}")
    check("has image_base64", "image_base64" in body, f"keys={list(body.keys())}")
    check("TradingView < 15s", elapsed < 15, f"took {elapsed:.1f}s")


def test_chart_render_no_data():
    print("\n── Chart Render (no data — validation) ──")
    code, body = _req("POST", "/v1/chart/render", {
        "chart_type": "candlestick",
        "title": "test",
        # no symbol, no data → should be 400
    })
    check("no symbol + no data returns 400 (not 500)", code == 400, f"got {code}: {body}")


def test_chart_render_local():
    print("\n── Chart Render (local mplfinance) ──")
    code, body = _req("POST", "/v1/chart/render", {
        "chart_type": "line",
        "title": "Test Line",
        "data": [
            {"date": "2025-01-01", "value": 100},
            {"date": "2025-01-02", "value": 105},
            {"date": "2025-01-03", "value": 102},
        ],
    })
    check("local line chart returns 200", code == 200, f"got {code}")
    check("has image_base64", "image_base64" in body)


def test_chart_render_feishu(full: bool = False):
    print("\n── Chart Render + Feishu Send ──")
    if not full:
        skip("chart_render + Feishu send (use --full)")
        return
    code, body = _req("POST", "/v1/chart/render", {
        "chart_type": "candlestick",
        "title": "AAPL K线图",
        "symbol": "AAPL",
        "asset_class": "stock",
        "open_id": OWNER_OPEN_ID,
    })
    check("chart + Feishu returns 200", code == 200, f"got {code}")
    check("sent_to is set", body.get("sent_to") == OWNER_OPEN_ID,
          f"sent_to={body.get('sent_to')}")


def test_browser_reuse():
    print("\n── Browser Reuse (consecutive calls) ──")
    # First call warms up the browser (may already be warm)
    _req("GET", "/v1/market/history?symbol=AAPL&asset_class=stock&days=5&chart=true")

    # Second call should be fast (browser reused)
    t0 = time.time()
    code, body = _req("GET", "/v1/market/history?symbol=MSFT&asset_class=stock&days=5&chart=true")
    elapsed = time.time() - t0
    check("reuse call returns 200", code == 200, f"got {code}")
    check("has chart", "chart_base64" in body)
    check("reuse call < 12s", elapsed < 12, f"took {elapsed:.1f}s")


def test_search():
    print("\n── Search ──")
    code, body = _req("GET", "/v1/search?q=test&top_k=3")
    check("search returns 200", code == 200, f"got {code}")
    check("has hits array", isinstance(body.get("hits"), list))


def test_daily_push_dry_run():
    print("\n── Daily Push (dry-run) ──")
    try:
        result = subprocess.run(
            ["python3", "daily_push.py", "--dry-run"],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        check("daily_push --dry-run exits 0", result.returncode == 0,
              f"exit={result.returncode}, stderr={result.stderr[-200:]}")
        # stdout should be valid JSON card
        card = None
        if result.returncode == 0 and result.stdout.strip():
            try:
                card = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                pass
        has_elements = card is not None and "header" in card and (
            "elements" in card or ("body" in card and "elements" in card.get("body", {}))
        )
        check("output is valid JSON card", has_elements,
              f"stdout[:200]={result.stdout[:200]}")
    except subprocess.TimeoutExpired:
        check("daily_push --dry-run completes within 120s", False, "timeout")
    except Exception as e:
        check("daily_push --dry-run runs", False, str(e))


def test_daily_push_send(full: bool = False):
    print("\n── Daily Push (send) ──")
    if not full:
        skip("daily_push actual send (use --full)")
        return
    try:
        result = subprocess.run(
            ["python3", "daily_push.py"],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        check("daily_push exits 0", result.returncode == 0,
              f"exit={result.returncode}, stderr={result.stderr[-200:]}")
    except Exception as e:
        check("daily_push runs", False, str(e))


def test_kol_push_dry_run():
    print("\n── KOL Push (dry-run) ──")
    try:
        result = subprocess.run(
            ["python3", "kol_push.py", "--dry-run"],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            timeout=180,
        )
        check("kol_push --dry-run exits 0", result.returncode == 0,
              f"exit={result.returncode}, stderr={result.stderr[-300:]}")
        card = None
        if result.returncode == 0 and result.stdout.strip():
            try:
                card = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass
        has_elements = card is not None and "header" in card and (
            "body" in card and "elements" in card.get("body", {})
        )
        check("output is valid JSON card", has_elements,
              f"stdout[:200]={result.stdout[:200]}")
    except subprocess.TimeoutExpired:
        check("kol_push --dry-run completes within 180s", False, "timeout")
    except Exception as e:
        check("kol_push --dry-run runs", False, str(e))


def test_kol_push_send(full: bool = False):
    print("\n── KOL Push (send) ──")
    if not full:
        skip("kol_push actual send (use --full)")
        return
    try:
        result = subprocess.run(
            ["python3", "kol_push.py"],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            timeout=180,
        )
        check("kol_push exits 0", result.returncode == 0,
              f"exit={result.returncode}, stderr={result.stderr[-300:]}")
    except Exception as e:
        check("kol_push runs", False, str(e))


def test_structurize_dry_run():
    print("\n── Structurize Dry Run ──")
    try:
        result = subprocess.run(
            ["python3", "structurize.py", "--layer", "1", "--limit", "1", "--dry-run"],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        check("structurize --dry-run exits 0", result.returncode == 0,
              f"exit={result.returncode}, stderr={result.stderr[-300:]}")
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                check("output is valid JSON with doc_id", "doc_id" in data,
                      f"keys={list(data.keys()) if isinstance(data, dict) else type(data)}")
            except json.JSONDecodeError:
                check("output is valid JSON", False, f"stdout[:200]={result.stdout[:200]}")
        else:
            skip("structurize output check", "no stdout or non-zero exit")
    except subprocess.TimeoutExpired:
        check("structurize --dry-run completes within 60s", False, "timeout")
    except Exception as e:
        check("structurize --dry-run runs", False, str(e))


def test_structured_api():
    print("\n── Structured Report API ──")
    code, body = _req("GET", "/v1/reports/structured?limit=5")
    check("GET /v1/reports/structured returns 200", code == 200, f"got {code}")
    check("has data array", isinstance(body.get("data"), list), f"keys={list(body.keys())}")

    code, body = _req("GET", "/v1/theses?limit=5")
    check("GET /v1/theses returns 200", code == 200, f"got {code}")
    check("has data array", isinstance(body.get("data"), list))

    code, body = _req("GET", "/v1/metrics?limit=5")
    check("GET /v1/metrics returns 200", code == 200, f"got {code}")
    check("has data array", isinstance(body.get("data"), list))

    code, body = _req("GET", "/v1/reports/stats")
    check("GET /v1/reports/stats returns 200", code == 200, f"got {code}")
    check("has total_eligible", "total_eligible" in body, f"keys={list(body.keys())}")

    # 404 for non-existent doc
    code, body = _req("GET", "/v1/reports/nonexistent-id/structured")
    check("GET /v1/reports/{bad_id}/structured returns 404", code == 404, f"got {code}")


def test_logs_clean():
    print("\n── Logs ──")
    if not os.path.exists(LOG_FILE):
        skip("log file not found", LOG_FILE)
        return
    with open(LOG_FILE) as f:
        content = f.read()
    has_error = "ERROR" in content or "Traceback" in content
    check("no ERROR/Traceback in logs", not has_error,
          "found error in " + LOG_FILE)
    # Check for our specific fixed bug
    thread_err = "cannot switch to a different thread" in content
    check("no thread-switch error", not thread_err)


# ── Server Management ──────────────────────────────────────────────────────


def restart_api():
    """Kill existing API, start fresh, wait for health."""
    print("\n── Restarting Query API ──")
    # Kill existing
    subprocess.run("lsof -ti:8788 | xargs kill -9 2>/dev/null", shell=True)
    time.sleep(2)

    # Start new
    proc = subprocess.Popen(
        ["python3", "query_api.py"],
        cwd=API_DIR,
        stdout=open(LOG_FILE, "w"),
        stderr=subprocess.STDOUT,
    )
    print(f"  Started PID {proc.pid}")

    # Wait for health
    for i in range(15):
        time.sleep(1)
        try:
            code, _ = _req("GET", "/health", timeout=3)
            if code == 200:
                print(f"  API healthy after {i+1}s")
                return True
        except Exception:
            pass
    print("  \033[31mAPI failed to start within 15s\033[0m")
    return False


def check_api_running() -> bool:
    """Check if API is already running."""
    try:
        code, _ = _req("GET", "/health", timeout=3)
        return code == 200
    except Exception:
        return False


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="贝多多 Query API Smoke Tests")
    parser.add_argument("--full", action="store_true", help="Run full tests including Feishu send")
    parser.add_argument("--restart", action="store_true", help="Restart API before testing")
    parser.add_argument("--quick", action="store_true", help="Quick mode: skip slow TradingView tests")
    args = parser.parse_args()

    print("=" * 60)
    print("贝多多 Query API — Smoke Test")
    print("=" * 60)

    # Ensure API is running
    if args.restart:
        if not restart_api():
            sys.exit(1)
    elif not check_api_running():
        print("\n\033[33mAPI not running. Starting it...\033[0m")
        if not restart_api():
            sys.exit(1)

    t_start = time.time()

    # Run tests
    test_health()
    test_search()
    test_market_quote()
    test_market_history(full=args.full)
    test_market_history_crypto()

    if not args.quick:
        test_chart_render_tradingview()
        test_chart_render_feishu(full=args.full)
        test_browser_reuse()

    test_chart_render_no_data()
    test_chart_render_local()
    test_daily_push_dry_run()
    test_daily_push_send(full=args.full)
    test_kol_push_dry_run()
    test_kol_push_send(full=args.full)
    test_structured_api()
    test_structurize_dry_run()
    test_logs_clean()

    elapsed = time.time() - t_start

    # Summary
    total = _pass + _fail + _skip
    print("\n" + "=" * 60)
    print(f"Results: \033[32m{_pass} passed\033[0m, \033[31m{_fail} failed\033[0m, "
          f"\033[33m{_skip} skipped\033[0m / {total} total  ({elapsed:.0f}s)")
    print("=" * 60)

    sys.exit(1 if _fail > 0 else 0)


if __name__ == "__main__":
    main()
