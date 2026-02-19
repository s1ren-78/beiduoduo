#!/usr/bin/env python3
"""
KOL 观点日报 — 每日推送到飞书（按用户隔离）。

Usage:
    python3 kol_push.py              # 抓取 + 摘要 + 分别推送给每个 owner
    python3 kol_push.py --dry-run    # 只输出 JSON 卡片（不发送）
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from lib.config import load_settings
from lib.db import DB
from lib.db_kol import get_distinct_owners
from lib.feishu_api import FeishuAuth, FeishuClient
from lib.jobs import ensure_schema
from lib.kol_briefing import (
    build_kol_card,
    fetch_all_kol_summaries,
    load_kol_config,
)

OWNER_OPEN_ID = "ou_ec332c4e35a82229099b7a04b89488ee"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("kol_push")


def main() -> None:
    parser = argparse.ArgumentParser(description="KOL 观点日报推送")
    parser.add_argument("--dry-run", action="store_true", help="Print card JSON without sending")
    args = parser.parse_args()

    settings = load_settings(str(Path(__file__).parent / ".env"))
    date_str = datetime.now().strftime("%Y-%m-%d")

    # ── DB for KOL watchlist ──
    kol_db = DB(settings.database_url)
    ensure_schema(kol_db, Path(__file__).parent / "schema.sql")

    # ── Get all owners who have KOLs ──
    owners = get_distinct_owners(kol_db)
    if not owners:
        # Fallback: try default owner
        owners = [OWNER_OPEN_ID]
    logger.info("Found %d owners with KOL watchlists", len(owners))

    if args.dry_run:
        # Dry run: use first owner (or default) for preview
        owner_id = owners[0] if owners else OWNER_OPEN_ID
        kols, kol_settings = load_kol_config(db=kol_db, owner_id=owner_id)
        logger.info("Loaded %d KOLs for owner %s", len(kols), owner_id)
        if not kols:
            logger.error("No KOLs configured for owner %s", owner_id)
            sys.exit(1)
        summaries = fetch_all_kol_summaries(kols, kol_settings)
        card = build_kol_card(summaries, date_str)
        print(json.dumps(card, ensure_ascii=False, indent=2))
        has_content = any(
            s.points and s.points != ["暂无新动态"] for s in summaries
        )
        logger.info(
            "Dry run complete. owner=%s, KOLs: %d, has_content: %s",
            owner_id, len(summaries), has_content,
        )
        return

    # ── Per-owner: fetch + summarize + send ──
    client = FeishuClient(FeishuAuth(app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret))

    total_sent = 0
    total_failed = 0

    for owner_id in owners:
        logger.info("── Processing owner: %s ──", owner_id)
        kols, kol_settings = load_kol_config(db=kol_db, owner_id=owner_id)
        logger.info("Loaded %d KOLs for owner %s", len(kols), owner_id)

        if not kols:
            logger.warning("No KOLs for owner %s, skipping", owner_id)
            continue

        summaries = fetch_all_kol_summaries(kols, kol_settings)
        card = build_kol_card(summaries, date_str)

        try:
            client.send_card_message(owner_id, card, receive_id_type="open_id")
            logger.info("Sent to %s", owner_id)
            total_sent += 1
        except Exception as e:
            logger.error("Failed to send to %s: %s", owner_id, e)
            total_failed += 1

    logger.info("Done. sent=%d, failed=%d", total_sent, total_failed)

    if total_sent == 0:
        logger.error("All sends failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
