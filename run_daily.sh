#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
WHITELIST="$ROOT/journal_whitelist_top40.txt"
TOPIC="${TOPIC:-llm}"
TOPIC_FILE="${TOPIC_FILE:-}"

cd "$ROOT"

if [[ -n "$TOPIC_FILE" ]]; then
  "$PYTHON" "$ROOT/pubmed_digest.py" \
    --days-back 3 \
    --topic-file "$TOPIC_FILE" \
    --candidate-pool-size 100 \
    --retmax 10 \
    --model gpt-5.4-nano \
    --final-model gpt-5.4 \
    --journal-whitelist "$WHITELIST"
else
  "$PYTHON" "$ROOT/pubmed_digest.py" \
    --days-back 3 \
    --topic "$TOPIC" \
    --candidate-pool-size 100 \
    --retmax 10 \
    --model gpt-5.4-nano \
    --final-model gpt-5.4 \
    --journal-whitelist "$WHITELIST"
fi

"$PYTHON" "$ROOT/editor_picks_from_pool.py"
