"""SEC EDGAR API client for US stock financial statements."""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class SECEdgarClient:
    """Fetches company financials from SEC EDGAR public API."""

    BASE_URL = "https://data.sec.gov"
    COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

    def __init__(self, user_agent: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
        })
        self._cik_cache: dict[str, str] = {}

    def _get(self, url: str) -> Any:
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def ticker_to_cik(self, ticker: str) -> str | None:
        ticker_upper = ticker.upper()
        if ticker_upper in self._cik_cache:
            return self._cik_cache[ticker_upper]
        try:
            data = self._get(self.COMPANY_TICKERS_URL)
            for entry in data.values():
                t = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", "")).zfill(10)
                self._cik_cache[t] = cik
                if t == ticker_upper:
                    return cik
        except Exception as e:
            logger.warning("SEC CIK lookup failed for %s: %s", ticker, e)
        return self._cik_cache.get(ticker_upper)

    def get_company_facts(self, ticker: str) -> dict[str, Any] | None:
        cik = self.ticker_to_cik(ticker)
        if not cik:
            logger.warning("CIK not found for ticker %s", ticker)
            return None
        try:
            return self._get(f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json")
        except Exception as e:
            logger.warning("SEC company facts failed for %s (CIK %s): %s", ticker, cik, e)
            return None

    def get_financials(self, ticker: str) -> list[dict[str, Any]]:
        facts = self.get_company_facts(ticker)
        if not facts:
            return []

        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        target_metrics = {
            "Revenues": "revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
            "NetIncomeLoss": "net_income",
            "GrossProfit": "gross_profit",
            "OperatingIncomeLoss": "operating_income",
            "EarningsPerShareBasic": "eps_basic",
            "EarningsPerShareDiluted": "eps_diluted",
            "Assets": "total_assets",
            "Liabilities": "total_liabilities",
            "StockholdersEquity": "stockholders_equity",
            "CashAndCashEquiventsAtCarryingValue": "cash",
            "OperatingCashFlow": "operating_cash_flow",
        }

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for gaap_key, metric_name in target_metrics.items():
            concept = us_gaap.get(gaap_key)
            if not concept:
                continue
            units = concept.get("units", {})
            unit_values = units.get("USD") or units.get("USD/shares") or []
            for entry in unit_values:
                form = entry.get("form", "")
                if form not in ("10-K", "10-Q"):
                    continue
                period = entry.get("end", "")
                if not period:
                    continue
                period_type = "annual" if form == "10-K" else "quarterly"
                key = (metric_name, period)
                if key in seen:
                    continue
                seen.add(key)

                unit_label = "USD"
                if "USD/shares" in units and gaap_key.startswith("EarningsPerShare"):
                    unit_label = "USD/share"

                rows.append({
                    "entity_id": ticker.upper(),
                    "entity_type": "stock",
                    "period": period,
                    "period_type": period_type,
                    "metric": metric_name,
                    "value": entry.get("val"),
                    "unit": unit_label,
                    "meta": {"form": form, "filed": entry.get("filed", "")},
                })

        return rows
