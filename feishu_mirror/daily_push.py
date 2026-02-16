#!/usr/bin/env python3
"""
Daily market ranking push to Feishu.

Usage:
    python3 daily_push.py              # Fetch data + send to all subscribers
    python3 daily_push.py --dry-run    # Fetch data + print card JSON (no send)
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
from lib.db import DB
from lib.ranking_data import (
    build_ranking_card,
    fetch_crypto_rankings,
    fetch_market_pulse,
    fetch_nasdaq_rankings,
    seed_default_pulse,
)

OWNER_OPEN_ID = "ou_ec332c4e35a82229099b7a04b89488ee"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("daily_push")


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily market ranking push")
    parser.add_argument("--dry-run", action="store_true", help="Print card JSON without sending")
    args = parser.parse_args()

    settings = load_settings(str(Path(__file__).parent / ".env"))
    db = DB(settings.database_url)
    seed_default_pulse(db)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # ── Fetch rankings ──
    rankings = []
    errors = []

    logger.info("Fetching NASDAQ rankings...")
    try:
        nasdaq_g, nasdaq_l = fetch_nasdaq_rankings()
        rankings.extend([nasdaq_g, nasdaq_l])
        if nasdaq_g.error:
            errors.append(f"NASDAQ gainers: {nasdaq_g.error}")
        if nasdaq_l.error:
            errors.append(f"NASDAQ losers: {nasdaq_l.error}")
    except Exception as e:
        logger.error("NASDAQ fetch crashed: %s", e)
        errors.append(f"NASDAQ: {e}")

    logger.info("Fetching Crypto rankings...")
    try:
        crypto_g, crypto_l = fetch_crypto_rankings(settings.artemis_api_key)
        rankings.extend([crypto_g, crypto_l])
        if crypto_g.error:
            errors.append(f"Crypto gainers: {crypto_g.error}")
        if crypto_l.error:
            errors.append(f"Crypto losers: {crypto_l.error}")
    except Exception as e:
        logger.error("Crypto fetch crashed: %s", e)
        errors.append(f"Crypto: {e}")

    if not rankings:
        logger.error("All data fetches failed, nothing to send")
        sys.exit(1)

    # ── Fetch market pulse (from watchlist label=pulse) ──
    pulse = None
    try:
        logger.info("Fetching market pulse...")
        pulse = fetch_market_pulse(settings.artemis_api_key, db=db)
        logger.info("Market pulse: %d items", len(pulse))
    except Exception as e:
        logger.warning("Market pulse fetch failed (non-fatal): %s", e)

    # ── Build card ──
    card = build_ranking_card(rankings, date_str, pulse=pulse)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        logger.info("Dry run complete. Rankings: %d sections, errors: %s", len(rankings), errors or "none")
        return

    # ── Resolve subscribers ──
    # Priority: DAILY_PUSH_OPEN_IDS env → auto-discover app visible users → owner fallback
    client = FeishuClient(FeishuAuth(app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret))

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

    logger.info("Done. sent=%d, failed=%d, data_errors=%s", sent, failed, errors or "none")

    if sent == 0:
        logger.error("All sends failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
