from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .db import DB
from .feishu_sync import sync_feishu
from .fin_sync import sync_financials
from .local_ingest import ingest_local
from .market_sync import sync_market


def _run_tracked(
    db: DB,
    scope: str,
    mode: str,
    reason: str,
    run_id: str | None,
    sync_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Generic wrapper: managed flag → start_sync_run → try/except → finish_sync_run.

    sync_fn receives the resolved run_id and returns a stats dict.
    """
    managed = run_id is None
    run_id = run_id or db.start_sync_run(scope, mode, reason)
    try:
        stats = sync_fn(run_id)
        if managed:
            db.finish_sync_run(run_id, "success", stats, None)
        return {"run_id": run_id, "status": "success", "stats": stats}
    except Exception as exc:
        if managed:
            db.finish_sync_run(run_id, "failed", {}, str(exc))
        raise


def run_local_sync(
    db: DB,
    settings: Settings,
    *,
    mode: str,
    reason: str = "manual",
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_tracked(db, "local", mode, reason, run_id, lambda rid: ingest_local(
        db, report_root=settings.report_root, incremental=(mode == "incremental"), run_id=rid,
    ).asdict())


def run_feishu_sync(
    db: DB,
    settings: Settings,
    *,
    mode: str,
    reason: str = "manual",
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_tracked(db, "feishu", mode, reason, run_id, lambda rid: sync_feishu(
        db,
        app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret,
        raw_root=settings.feishu_raw_root, page_size=settings.sync_page_size,
        retry_max=settings.sync_retry_max, retry_backoff_ms=settings.sync_retry_backoff_ms,
        incremental=(mode == "incremental"), run_id=rid,
    ).asdict())


def run_all_sync(
    db: DB,
    settings: Settings,
    *,
    mode: str,
    reason: str = "manual",
    run_id: str | None = None,
) -> dict[str, Any]:
    incremental = mode == "incremental"

    def _sync(rid: str) -> dict[str, Any]:
        local_stats = ingest_local(
            db, report_root=settings.report_root, incremental=incremental, run_id=rid,
        ).asdict()
        feishu_stats = sync_feishu(
            db,
            app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret,
            raw_root=settings.feishu_raw_root, page_size=settings.sync_page_size,
            retry_max=settings.sync_retry_max, retry_backoff_ms=settings.sync_retry_backoff_ms,
            incremental=incremental, run_id=rid,
        ).asdict()
        return {"local": local_stats, "feishu": feishu_stats}

    return _run_tracked(db, "all", mode, reason, run_id, _sync)


def run_market_sync(
    db: DB,
    settings: Settings,
    *,
    mode: str,
    reason: str = "manual",
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_tracked(db, "market", mode, reason, run_id, lambda rid: sync_market(
        db, settings, mode=mode, run_id=rid,
    ).asdict())


def run_financials_sync(
    db: DB,
    settings: Settings,
    *,
    mode: str,
    reason: str = "manual",
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_tracked(db, "financials", mode, reason, run_id, lambda rid: sync_financials(
        db, settings, mode=mode, run_id=rid,
    ).asdict())


def ensure_schema(db: DB, schema_file: Path) -> None:
    db.ensure_schema(schema_file)
