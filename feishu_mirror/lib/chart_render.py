from __future__ import annotations

import atexit
import io
import logging
import platform
import threading

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


_CN_FONT_NAME: str | None = None


def _setup_chinese_font() -> None:
    """Auto-detect Chinese font on macOS / Linux."""
    global _CN_FONT_NAME
    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS"]
    elif system == "Linux":
        candidates = ["WenQuanYi Micro Hei", "Noto Sans CJK SC", "Droid Sans Fallback"]

    for font in candidates:
        try:
            matplotlib.font_manager.findfont(font, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [font] + plt.rcParams.get("font.sans-serif", [])
            plt.rcParams["axes.unicode_minus"] = False
            _CN_FONT_NAME = font
            return
        except Exception:
            continue


_setup_chinese_font()


def _parse_dates(series: list[dict]) -> tuple[list[datetime], list[float]]:
    dates = []
    values = []
    for item in series:
        d = item.get("date") or item.get("trade_date") or item.get("period", "")
        v = item.get("value") or item.get("close") or item.get("price", 0)
        if isinstance(d, str):
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    d = datetime.strptime(d, fmt)
                    break
                except ValueError:
                    continue
        dates.append(d)
        values.append(float(v))
    return dates, values


def _setup_date_axis(ax: plt.Axes, num_points: int) -> None:
    """Smart date axis: use AutoDateLocator to avoid duplicate labels."""
    locator = mdates.AutoDateLocator(minticks=3, maxticks=min(num_points, 12))
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))


def _finalize(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_line_chart(
    series: list[dict],
    title: str,
    y_label: str = "",
    size: tuple = (10, 5),
) -> bytes:
    """Render a single line chart, return PNG bytes."""
    dates, values = _parse_dates(series)

    fig, ax = plt.subplots(figsize=size)
    ax.plot(dates, values, linewidth=1.8, color="#4C8BF5")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    if y_label:
        ax.set_ylabel(y_label)
    ax.grid(True, alpha=0.3)
    _setup_date_axis(ax, len(dates))
    fig.autofmt_xdate(rotation=30)
    ax.fill_between(dates, values, alpha=0.08, color="#4C8BF5")

    return _finalize(fig)


def render_multi_line_chart(
    series_list: list[dict],
    title: str,
    y_label: str = "",
    size: tuple = (10, 5),
) -> bytes:
    """Render multiple lines. series_list: [{"label": "AAPL", "data": [{"date":..., "value":...}]}]"""
    colors = ["#4C8BF5", "#EA4335", "#FBBC04", "#34A853", "#FF6D01", "#46BDC6"]
    fig, ax = plt.subplots(figsize=size)

    for i, s in enumerate(series_list):
        dates, values = _parse_dates(s["data"])
        color = colors[i % len(colors)]
        ax.plot(dates, values, linewidth=1.8, color=color, label=s.get("label", f"Series {i+1}"))

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    if y_label:
        ax.set_ylabel(y_label)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    max_pts = max((len(s["data"]) for s in series_list), default=0)
    _setup_date_axis(ax, max_pts)
    fig.autofmt_xdate(rotation=30)

    return _finalize(fig)


def render_bar_chart(
    series: list[dict],
    title: str,
    y_label: str = "",
    size: tuple = (10, 5),
) -> bytes:
    """Render a bar chart. series: [{"label": "Q1", "value": 123}, ...]"""
    labels = [item.get("label") or item.get("date") or item.get("period", "") for item in series]
    values = [float(item.get("value", 0)) for item in series]

    fig, ax = plt.subplots(figsize=size)
    bars = ax.bar(range(len(labels)), values, color="#4C8BF5", width=0.6)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    if y_label:
        ax.set_ylabel(y_label)
    ax.grid(True, axis="y", alpha=0.3)

    # Value labels on bars
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{val:,.0f}",
            ha="center", va="bottom", fontsize=8,
        )

    return _finalize(fig)


_NYSE_SYMBOLS = frozenset({
    "IBM", "GE", "GS", "JPM", "BAC", "WFC", "C", "MS", "V", "MA",
    "JNJ", "PG", "KO", "PEP", "WMT", "DIS", "NKE", "MCD", "BA",
    "CVX", "XOM", "CAT", "MMM", "HD", "UNH", "PFE", "MRK", "ABT",
    "T", "VZ", "GM", "F", "BRK.A", "BRK.B", "BABA", "TSM", "COIN",
})


def _tv_symbol(symbol: str, asset_class: str) -> str:
    """Map symbol + asset_class to TradingView exchange:symbol format."""
    s = symbol.upper()
    if asset_class == "crypto":
        s = s.replace("USDT", "").replace("USD", "")
        return f"BINANCE:{s}USDT"
    else:
        exchange = "NYSE" if s in _NYSE_SYMBOLS else "NASDAQ"
        return f"{exchange}:{s}"


_log = logging.getLogger(__name__)

_pw_lock = threading.Lock()
_playwright_instance = None
_browser_instance = None


def _get_browser():
    """Lazy-init persistent Playwright browser (thread-safe, auto-recover)."""
    global _playwright_instance, _browser_instance
    with _pw_lock:
        if _browser_instance is not None:
            try:
                if _browser_instance.is_connected():
                    return _browser_instance
            except Exception:
                pass
            # Browser died — clean up and recreate
            _browser_instance = None

        if _playwright_instance is not None:
            try:
                _playwright_instance.stop()
            except Exception:
                pass
            _playwright_instance = None

        from playwright.sync_api import sync_playwright
        _playwright_instance = sync_playwright().start()
        _browser_instance = _playwright_instance.chromium.launch(headless=True)
        return _browser_instance


def _cleanup_playwright():
    """Shutdown browser on process exit to avoid zombie Chromium."""
    global _playwright_instance, _browser_instance
    try:
        if _browser_instance:
            _browser_instance.close()
    except Exception:
        pass
    try:
        if _playwright_instance:
            _playwright_instance.stop()
    except Exception:
        pass
    _browser_instance = None
    _playwright_instance = None


atexit.register(_cleanup_playwright)


def render_tradingview_screenshot(
    symbol: str,
    asset_class: str = "stock",
    interval: str = "D",
    size: tuple = (1280, 800),
) -> bytes:
    """Screenshot TradingView chart for the given symbol via headless Playwright."""
    tv_sym = _tv_symbol(symbol, asset_class)
    url = f"https://www.tradingview.com/chart/?symbol={tv_sym}&interval={interval}&theme=dark"

    browser = _get_browser()
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    try:
        # Use "domcontentloaded" instead of "networkidle" — TradingView loads tons
        # of JS/analytics that "networkidle" waits for unnecessarily (~20s).
        # The canvas selector below catches when the chart is actually rendered.
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector("canvas", timeout=10000)
        page.wait_for_timeout(1500)  # let final chart paint finish
        return page.screenshot(type="png")
    except Exception as exc:
        _log.warning("TradingView screenshot failed for %s: %s", symbol, exc)
        raise
    finally:
        try:
            page.close()
        except Exception:
            pass


def render_candlestick_chart(
    series: list[dict],
    title: str,
    y_label: str = "",
    size: tuple = (12, 7),
) -> bytes:
    """Render a candlestick (K-line) chart from OHLCV data, return PNG bytes.

    series: [{"date": "2025-02-10", "open": 150, "high": 155, "low": 148, "close": 152, "volume": 1000000}, ...]
    """
    import mplfinance as mpf
    import pandas as pd

    rows = []
    for item in series:
        d = item.get("date") or item.get("trade_date") or item.get("period", "")
        rows.append({
            "Date": pd.Timestamp(d),
            "Open": float(item.get("open", 0)),
            "High": float(item.get("high", 0)),
            "Low": float(item.get("low", 0)),
            "Close": float(item.get("close", 0)),
            "Volume": float(item.get("volume", 0)),
        })

    df = pd.DataFrame(rows)
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)

    has_volume = bool(df["Volume"].sum() > 0)

    mc = mpf.make_marketcolors(
        up="#CF3040", down="#00B386",       # 涨红跌绿
        edge="inherit", wick="inherit",
        volume={"up": "#CF304088", "down": "#00B38688"},
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        gridstyle="--", gridcolor="#333333",
        facecolor="#1A1A2E", edgecolor="#333333",
        figcolor="#1A1A2E",
        y_on_right=True,
        rc={
            "font.size": 10,
            "font.sans-serif": [_CN_FONT_NAME, "DejaVu Sans"] if _CN_FONT_NAME else ["DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.labelcolor": "#CCCCCC",
            "xtick.color": "#AAAAAA",
            "ytick.color": "#AAAAAA",
        },
    )

    # Add moving averages if enough data
    mav = ()
    if len(df) >= 20:
        mav = (5, 10, 20)
    elif len(df) >= 10:
        mav = (5, 10)
    elif len(df) >= 5:
        mav = (5,)

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        title=title,
        ylabel=y_label or "Price",
        volume=has_volume,
        mav=mav,
        figsize=size,
        returnfig=True,
        tight_layout=True,
    )

    # Style the title
    if axes:
        axes[0].set_title(
            title, fontsize=15, fontweight="bold", color="white",
            pad=12,
            fontfamily=_CN_FONT_NAME or "sans-serif",
        )

    return _finalize(fig)
