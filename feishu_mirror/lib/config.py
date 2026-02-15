from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    report_root: Path
    report_index_root: Path
    feishu_raw_root: Path
    feishu_checkpoint_root: Path
    feishu_export_root: Path
    feishu_app_id: str
    feishu_app_secret: str
    sync_page_size: int
    sync_retry_max: int
    sync_retry_backoff_ms: int
    default_top_k: int
    query_api_host: str
    query_api_port: int
    artemis_api_key: str
    sec_edgar_user_agent: str
    market_incremental_minutes: int
    financials_incremental_minutes: int
    market_history_days: int
    brave_search_api_key: str


def load_settings(env_file: str | None = None) -> Settings:
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    report_root = Path(os.getenv("REPORT_ROOT", "/Users/beiduoudo/Desktop/贝多多/数据库")).expanduser()
    report_index_root = Path(
        os.getenv("REPORT_INDEX_ROOT", "/Users/beiduoudo/Desktop/贝多多/数据库/_index")
    ).expanduser()

    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", str(report_index_root / "beiduoduo.db")
        ),
        report_root=report_root,
        report_index_root=report_index_root,
        feishu_raw_root=Path(
            os.getenv("FEISHU_RAW_ROOT", str(report_index_root / "raw"))
        ).expanduser(),
        feishu_checkpoint_root=Path(
            os.getenv("FEISHU_CHECKPOINT_ROOT", str(report_index_root / "checkpoints"))
        ).expanduser(),
        feishu_export_root=Path(
            os.getenv("FEISHU_EXPORT_ROOT", str(report_index_root / "exports"))
        ).expanduser(),
        feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
        sync_page_size=int(os.getenv("SYNC_PAGE_SIZE", "200")),
        sync_retry_max=int(os.getenv("SYNC_RETRY_MAX", "5")),
        sync_retry_backoff_ms=int(os.getenv("SYNC_RETRY_BACKOFF_MS", "800")),
        default_top_k=int(os.getenv("DEFAULT_TOP_K", "8")),
        query_api_host=os.getenv("QUERY_API_HOST", "127.0.0.1"),
        query_api_port=int(os.getenv("QUERY_API_PORT", "8788")),
        artemis_api_key=os.getenv("ARTEMIS_API_KEY", ""),
        sec_edgar_user_agent=os.getenv("SEC_EDGAR_USER_AGENT", ""),
        market_incremental_minutes=int(os.getenv("MARKET_INCREMENTAL_MINUTES", "60")),
        financials_incremental_minutes=int(os.getenv("FINANCIALS_INCREMENTAL_MINUTES", "720")),
        market_history_days=int(os.getenv("MARKET_HISTORY_DAYS", "365")),
        brave_search_api_key=os.getenv("BRAVE_SEARCH_API_KEY", ""),
    )


def ensure_runtime_dirs(settings: Settings) -> None:
    for path in (
        settings.report_root,
        settings.report_index_root,
        settings.feishu_raw_root,
        settings.feishu_checkpoint_root,
        settings.feishu_export_root,
        settings.report_index_root / "logs",
    ):
        path.mkdir(parents=True, exist_ok=True)
