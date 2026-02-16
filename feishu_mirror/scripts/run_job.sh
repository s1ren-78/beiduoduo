#!/bin/zsh
# Wrapper for launchd jobs — bypasses macOS TCC restriction on python3
# by reading the script file via zsh (which has Desktop access) and
# piping it into python3 via stdin.
set -euo pipefail
SCRIPT_DIR="/Users/beiduoudo/Desktop/贝多多/feishu_mirror"
cd "$SCRIPT_DIR"
exec /usr/bin/python3 - < "$SCRIPT_DIR/$1"
