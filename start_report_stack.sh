#!/bin/zsh
set -euo pipefail

ROOT="/Users/beiduoudo/Desktop/贝多多"
API_DIR="$ROOT/feishu_mirror"
LOG_DIR="$ROOT/数据库/_index/logs"
mkdir -p "$LOG_DIR"

# PostgreSQL preflight (required by query_api.py)
if ! nc -z 127.0.0.1 5432 >/dev/null 2>&1; then
  echo "PostgreSQL is not reachable at 127.0.0.1:5432. Start Postgres.app first."
fi

# Start Query API
pkill -f "python3 .*feishu_mirror/query_api.py" >/dev/null 2>&1 || true
nohup /usr/bin/python3 "$API_DIR/query_api.py" > "$LOG_DIR/query_api.log" 2>&1 &

# Restart OpenClaw gateway to reload plugin/prompt
pkill -f "openclaw.*gateway" >/dev/null 2>&1 || true
nohup /Users/beiduoudo/.openclaw/bin/openclaw gateway run > /Users/beiduoudo/Desktop/贝多多/.openclaw/logs/gateway.manual.log 2>&1 &

sleep 3
/Users/beiduoudo/.openclaw/bin/openclaw status
if ! curl -sS http://127.0.0.1:8788/health >/dev/null 2>&1; then
  echo "Query API is not healthy. Check: $LOG_DIR/query_api.log"
fi
