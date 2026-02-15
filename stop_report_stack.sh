#!/bin/zsh
set -euo pipefail

pkill -f "python3 .*feishu_mirror/query_api.py" >/dev/null 2>&1 || true
pkill -f "openclaw.*gateway" >/dev/null 2>&1 || true
sleep 1
/Users/beiduoudo/.openclaw/bin/openclaw status
