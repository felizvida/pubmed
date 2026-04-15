#!/bin/bash
set -euo pipefail

ROOT="/Users/liux17/codex/pubmed"
PYTHON="/Users/liux17/miniforge/envs/pandas/bin/python"
WHITELIST="$ROOT/journal_whitelist_top40.txt"

cd "$ROOT"

"$PYTHON" "$ROOT/pubmed_digest.py" \
  --days-back 365 \
  --candidate-pool-size 50 \
  --retmax 10 \
  --journal-whitelist "$WHITELIST"

"$PYTHON" "$ROOT/editor_picks_from_pool.py"
