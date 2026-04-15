# PubMed LLM Digest

This is a small daily pipeline for finding newly added PubMed papers related to LLMs, pulling the abstract plus PMC full text when available, and ranking them into a recommended-reading digest with the OpenAI API.

## What it does

- Searches PubMed for recent LLM-related additions using the article `edat` window.
- Pulls paper metadata, abstract text, and PMC full text when a PubMed record links to PMC.
- Scores each paper for LLM relevance, impact, rigor, and interestingness with OpenAI.
- Also captures `awe_factor` and `surprise_factor` to highlight especially impressive or unexpected papers.
- Writes a Markdown digest and a JSON export under `output/`.
- Tracks already-seen PMIDs in `data/pubmed_digest.sqlite3` so daily runs stay incremental.

## Quick start

Create a local `.env` file and run the digest with the `pandas` conda env Python:

```bash
cat > /Users/liux17/codex/pubmed/.env <<'EOF'
OPENAI_API_KEY="your-openai-key"
EOF
/Users/liux17/miniforge/envs/pandas/bin/python /Users/liux17/codex/pubmed/pubmed_digest.py
```

Optional NCBI settings:

```bash
export NCBI_API_KEY="your-ncbi-key"
export NCBI_EMAIL="you@example.com"
```

The script loads `/Users/liux17/codex/pubmed/.env` automatically. That file is ignored by git.

If `OPENAI_API_KEY` is missing, the script still collects new papers and writes an unscored digest.

## Useful flags

```bash
/Users/liux17/miniforge/envs/pandas/bin/python /Users/liux17/codex/pubmed/pubmed_digest.py \
  --days-back 2 \
  --retmax 40 \
  --model gpt-5.4-nano
```

Important options:

- `--query`: override the PubMed query.
- `--days-back`: search N recent days of PubMed additions.
- `--retmax`: cap the number of papers inspected.
- `--full-text-char-limit`: trim long PMC full text before LLM scoring.
- `--mark-seen-without-scoring`: still mark papers as handled when no OpenAI key is set.
- `--mark-seen-on-error`: mark papers as handled even if OpenAI scoring fails.

## Daily scheduling

One simple cron setup is:

```cron
0 7 * * * cd /Users/liux17/codex/pubmed && /Users/liux17/miniforge/envs/pandas/bin/python /Users/liux17/codex/pubmed/pubmed_digest.py >> /Users/liux17/codex/pubmed/output/cron.log 2>&1
```

That runs every day at 7:00 AM in your local machine time zone.

## Output

Each run writes:

- `output/pubmed-digest-YYYYMMDD-HHMMSS.md`
- `output/pubmed-digest-YYYYMMDD-HHMMSS.json`

The Markdown file is the human-readable reading list. The JSON file is useful if you later want to build an emailer, Slack bot, or simple web UI.

## Notes

- PubMed does not guarantee full paper text for every record. This pipeline uses PMC full text when available and falls back to abstract-only ranking otherwise.
- The default query is intentionally broad. You will probably want to tighten it once you see what kinds of papers you personally care about.
