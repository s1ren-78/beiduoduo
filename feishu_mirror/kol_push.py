#!/usr/bin/env python3
"""
KOL 观点日报 — 每日推送到飞书。

Usage:
    python3 kol_push.py              # 抓取 + 摘要 + 发送飞书
    python3 kol_push.py --dry-run    # 只输出 JSON 卡片（不发送）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from lib.config import load_settings
from lib.feishu_api import FeishuAuth, FeishuClient
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

    # ── Load KOL config ──
    kols, kol_settings = load_kol_config()
    logger.info("Loaded %d KOLs", len(kols))

    if not kols:
        logger.error("No KOLs configured")
        sys.exit(1)

    # ── Fetch + summarize ──
    summaries = fetch_all_kol_summaries(kols, kol_settings)

    # ── Build card ──
    card = build_kol_card(summaries, date_str)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        has_content = any(
            s.points and s.points != ["暂无新动态"] for s in summaries
        )
        logger.info(
            "Dry run complete. KOLs: %d, has_content: %s",
            len(summaries), has_content,
        )
        return

    # ── Resolve subscribers ──
    client = FeishuClient(FeishuAuth(app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret))

    # Priority: KOL_PUSH_OPEN_IDS → DAILY_PUSH_OPEN_IDS → auto-discover → owner
    open_ids_str = os.getenv("KOL_PUSH_OPEN_IDS", "").strip()
    if not open_ids_str:
        open_ids_str = os.getenv("DAILY_PUSH_OPEN_IDS", "").strip()

    if open_ids_str and open_ids_str.lower() != "auto":
        open_ids = [oid.strip() for oid in open_ids_str.split(",") if oid.strip()]
        logger.info("Using env subscriber list: %d users", len(open_ids))
    else:
        logger.info("Auto-discovering app visible users...")
        open_ids = client.list_app_visible_users(settings.feishu_app_id)
        if open_ids:
            logger.info("Found %d authorized users", len(open_ids))
        else:
            logger.warning("No users discovered, falling back to owner")
            open_ids = [OWNER_OPEN_ID]

    # ── Send ──
    sent = 0
    failed = 0
    for oid in open_ids:
        try:
            client.send_card_message(oid, card, receive_id_type="open_id")
            logger.info("Sent to %s", oid)
            sent += 1
        except Exception as e:
            logger.error("Failed to send to %s: %s", oid, e)
            failed += 1

    logger.info("Done. sent=%d, failed=%d", sent, failed)

    if sent == 0:
        logger.error("All sends failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
