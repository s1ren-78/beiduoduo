#!/bin/zsh
set -euo pipefail

OPENCLAW_BIN="/Users/beiduoudo/.openclaw/bin/openclaw"

accounts=("default")
failed=0

extract_json() {
  awk 'BEGIN{start=0} /^[[:space:]]*[{]/{start=1} {if(start) print}'
}

echo "== Feishu Account Probe =="
for acc in "${accounts[@]}"; do
  raw="$($OPENCLAW_BIN channels capabilities --channel feishu --account "$acc" --json 2>/dev/null)"
  json="$(echo "$raw" | extract_json)"
  ok="$(echo "$json" | jq -r '.channels[0].probe.ok // false')"
  app_id="$(echo "$json" | jq -r '.channels[0].probe.appId // "-"')"
  err="$(echo "$json" | jq -r '.channels[0].probe.error // ""')"
  if [[ "$ok" == "true" ]]; then
    bot_open_id="$(echo "$json" | jq -r '.channels[0].probe.botOpenId // "-"')"
    echo "[OK]    $acc  appId=$app_id  botOpenId=$bot_open_id"
  else
    echo "[FAIL]  $acc  appId=$app_id  error=$err"
    failed=1
  fi
done

echo
echo "== OpenClaw Status Summary =="
$OPENCLAW_BIN status | sed -n '1,120p'

echo
echo "== Report Plugin =="
$OPENCLAW_BIN plugins info openclaw-report-db | sed -n '1,120p'

if [[ $failed -ne 0 ]]; then
  echo
  echo "Result: NOT READY"
  exit 1
fi

echo
echo "Result: READY (all Feishu accounts healthy)"
