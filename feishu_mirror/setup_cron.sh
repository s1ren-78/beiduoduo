#!/bin/zsh
set -euo pipefail

ROOT="/Users/beiduoudo/Desktop/贝多多/feishu_mirror"
PY="/usr/bin/python3"

TMP="$(mktemp)"
crontab -l 2>/dev/null > "$TMP" || true

# Remove older beiduoduo mirror jobs.
grep -v "beiduoduo-feishu-mirror" "$TMP" > "$TMP.filtered" || true
mv "$TMP.filtered" "$TMP"

cat >> "$TMP" <<CRON
*/10 * * * * cd "$ROOT" && $PY ingest_local_incremental.py >> /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/local_incremental.log 2>&1 # beiduoduo-feishu-mirror
*/15 * * * * cd "$ROOT" && $PY sync_feishu_incremental.py >> /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/feishu_incremental.log 2>&1 # beiduoduo-feishu-mirror
30 2 * * * cd "$ROOT" && $PY sync_all_full.py >> /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/full_reconcile.log 2>&1 # beiduoduo-feishu-mirror
0 8 * * * cd "$ROOT" && $PY daily_push.py >> /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/daily_push.log 2>&1 # beiduoduo-feishu-mirror
CRON

crontab "$TMP"
rm -f "$TMP"
echo "Cron installed for beiduoduo-feishu-mirror"
