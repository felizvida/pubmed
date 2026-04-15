# PubMed LLM Digest

Daily, journal-aware discovery and ranking of new PubMed papers about LLMs, foundation models, and adjacent AI methods.

This project builds a candidate pool from reputable journals, expands to `MEDLINE[sb]` only if needed, reads abstracts or PMC full text, and produces a polished daily reading list plus editor's picks.

## Highlights

- Finds newly added PubMed papers using the article `edat` window.
- Uses a curated `top40` journal whitelist first, then falls back to `MEDLINE[sb]` to fill a target candidate pool.
- Scores papers with OpenAI across relevance, impact, rigor, interestingness, `awe_factor`, and `surprise_factor`.
- Produces editor's picks for:
  - theoretical contribution
  - impactful application
  - fun / surprising paper
- Writes clean daily outputs into `output/YYYY-MM-DD/`.
- Tracks already-seen PMIDs in SQLite so recurring runs stay incremental.

## Repository Layout

- `pubmed_digest.py`: main retrieval, scoring, and digest writer
- `editor_picks_from_pool.py`: editor's-picks selection from the daily candidate pool
- `run_daily.sh`: one-command daily runner for terminal use
- `journal_whitelist_top40.txt`: curated journal whitelist
- `output/YYYY-MM-DD/`: generated daily Markdown and JSON files
- `data/pubmed_digest.sqlite3`: local incremental state

## Quick Start

Create a local `.env` file:

```bash
cat > /Users/liux17/codex/pubmed/.env <<'EOF'
OPENAI_API_KEY="your-openai-key"
NCBI_API_KEY="your-ncbi-key"
NCBI_EMAIL="you@example.com"
EOF
```

Then run the daily workflow:

```bash
/Users/liux17/codex/pubmed/run_daily.sh
```

The scripts automatically load `/Users/liux17/codex/pubmed/.env`. That file is ignored by git.

## How It Works

1. Search PubMed for recent LLM-related papers.
2. Fill a candidate pool from the journal whitelist first.
3. If the pool is still too small, search `MEDLINE[sb]` as a fallback.
4. Fetch summaries, abstracts, and PMC full text when available.
5. Rank candidates with OpenAI.
6. Write:
   - a full digest
   - a machine-readable JSON export
   - a separate editor's picks summary

## Terminal Usage

Run the full workflow:

```bash
/Users/liux17/codex/pubmed/run_daily.sh
```

Run the main digest only:

```bash
cd /Users/liux17/codex/pubmed
/Users/liux17/miniforge/envs/pandas/bin/python pubmed_digest.py \
  --days-back 365 \
  --candidate-pool-size 50 \
  --retmax 10 \
  --journal-whitelist /Users/liux17/codex/pubmed/journal_whitelist_top40.txt
```

Run editor's picks only:

```bash
cd /Users/liux17/codex/pubmed
/Users/liux17/miniforge/envs/pandas/bin/python editor_picks_from_pool.py
```

## Important Flags

- `--query`: override the default PubMed query
- `--days-back`: search N recent days of PubMed additions
- `--candidate-pool-size`: build up to this many candidates before ranking
- `--retmax`: number of fetched/scored papers to include in the digest
- `--journal-whitelist`: newline-delimited whitelist file
- `--full-text-char-limit`: trim long PMC full text before sending to the model
- `--mark-seen-without-scoring`: persist PMIDs even when no OpenAI key is set
- `--mark-seen-on-error`: persist PMIDs even when OpenAI scoring fails

## Output

Each run writes into a date folder:

- `output/YYYY-MM-DD/digest.md`
- `output/YYYY-MM-DD/digest.json`
- `output/YYYY-MM-DD/editor-picks.md`
- `output/YYYY-MM-DD/editor-picks.json`

`digest.md` is the main human-readable reading list.  
`editor-picks.md` is the shorter editorial summary.  
The JSON files are useful for automation, Slack/email formatting, or downstream tools.

## Scheduling

Example cron entry:

```cron
0 7 * * * cd /Users/liux17/codex/pubmed && /Users/liux17/codex/pubmed/run_daily.sh >> /Users/liux17/codex/pubmed/output/cron.log 2>&1
```

That runs every day at 7:00 AM in the machine's local time zone.

## Notes

- PubMed does not guarantee full paper text for every record. The pipeline uses PMC full text when available and falls back to abstract-only ranking otherwise.
- The default query is intentionally broad, but the journal-first retrieval strategy keeps the recommendation quality much higher than a raw PubMed scrape.
- Secrets stay local in `.env`; generated outputs and local state are ignored by git.
