#!/bin/zsh
set -euo pipefail

PLUGIN_SRC="/Users/beiduoudo/Desktop/贝多多/report-db-plugin"
OPENCLAW_BIN="/Users/beiduoudo/.openclaw/bin/openclaw"

$OPENCLAW_BIN plugins install "$PLUGIN_SRC" || true
$OPENCLAW_BIN plugins list | sed -n '1,120p'
