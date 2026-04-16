#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
WHITELIST="$ROOT/journal_whitelist_top40.txt"
TOPIC="${TOPIC:-llm}"
TOPIC_FILE="${TOPIC_FILE:-}"
DAYS_BACK="${DAYS_BACK:-${PUBMED_DAYS_BACK:-3}}"

cd "$ROOT"
export PUBMED_TOPIC="$TOPIC"
if [[ -n "$TOPIC_FILE" ]]; then
  export PUBMED_TOPIC_FILE="$TOPIC_FILE"
else
  unset PUBMED_TOPIC_FILE
fi

if [[ -n "$TOPIC_FILE" ]]; then
  "$PYTHON" "$ROOT/pubmed_digest.py" \
    --days-back "$DAYS_BACK" \
    --topic-file "$TOPIC_FILE" \
    --candidate-pool-size 100 \
    --retmax 10 \
    --model gpt-5.4-mini \
    --final-model gpt-5.4 \
    --journal-whitelist "$WHITELIST"
else
  "$PYTHON" "$ROOT/pubmed_digest.py" \
    --days-back "$DAYS_BACK" \
    --topic "$TOPIC" \
    --candidate-pool-size 100 \
    --retmax 10 \
    --model gpt-5.4-mini \
    --final-model gpt-5.4 \
    --journal-whitelist "$WHITELIST"
fi

"$PYTHON" "$ROOT/editor_picks_from_pool.py"

"$PYTHON" "$ROOT/post_to_slack.py"
