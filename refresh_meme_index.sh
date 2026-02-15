#!/bin/zsh
set -euo pipefail
cd '/Users/beiduoudo/Desktop/贝多多/.openclaw/workspace/memes'
{
  echo '# Meme Index'
  echo
  echo "Generated at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo '## Non-Market (daily)'
  find ./cute ./casual ./happy ./funny -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.webp' \) 2>/dev/null | sort | sed 's#^./#- #'
  echo
  echo '## Market-Up (market context only)'
  find ./上涨 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.webp' \) 2>/dev/null | sort | sed 's#^./#- #'
  echo
  echo '## Market-Down (market context only)'
  find ./下跌 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.webp' \) 2>/dev/null | sort | sed 's#^./#- #'
} > INDEX.md
printf 'Meme index refreshed: %s\n' '/Users/beiduoudo/Desktop/贝多多/.openclaw/workspace/memes/INDEX.md'
