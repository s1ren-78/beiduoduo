#!/usr/bin/env python3
"""Unified sync CLI — replaces 10 individual sync/ingest scripts.

Usage:
    python3 sync.py --scope local --mode incremental
    python3 sync.py --scope all --mode full --reason schedule
"""
from __future__ import annotations

import argparse
from pathlib import Path

from lib.config import ensure_runtime_dirs, load_settings
from lib.db import DB
from lib.jobs import (
    ensure_schema,
    run_all_sync,
    run_feishu_sync,
    run_financials_sync,
    run_local_sync,
    run_market_sync,
)

_RUNNERS = {
    "local": run_local_sync,
    "feishu": run_feishu_sync,
    "all": run_all_sync,
    "market": run_market_sync,
    "financials": run_financials_sync,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Beiduoduo unified sync")
    parser.add_argument("--scope", required=True, choices=_RUNNERS.keys())
    parser.add_argument("--mode", required=True, choices=["full", "incremental"])
    parser.add_argument("--reason", default="schedule", choices=["manual", "schedule", "miss"])
    args = parser.parse_args()

    settings = load_settings(str(Path(__file__).parent / ".env"))
    ensure_runtime_dirs(settings)
    db = DB(settings.database_url)
    ensure_schema(db, Path(__file__).parent / "schema.sql")

    result = _RUNNERS[args.scope](db, settings, mode=args.mode, reason=args.reason)
    print(result)


if __name__ == "__main__":
    main()
