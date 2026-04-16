#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
WHITELIST="$ROOT/journal_whitelist_top40.txt"

cd "$ROOT"

"$PYTHON" "$ROOT/pubmed_digest.py" \
  --days-back 3 \
  --candidate-pool-size 100 \
  --retmax 10 \
  --model gpt-5.4-nano \
  --final-model gpt-5.4 \
  --journal-whitelist "$WHITELIST"

"$PYTHON" "$ROOT/editor_picks_from_pool.py"
