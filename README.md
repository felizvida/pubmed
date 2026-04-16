# PubMed Signal

![PubMed Signal banner](assets/banner.svg)

Daily, journal-aware discovery and ranking of recent PubMed, bioRxiv, and arXiv papers on your chosen AI-related research topic.

This project builds a candidate pool from reputable journals, expands to `MEDLINE[sb]` only if needed, then reaches into bioRxiv and the arXiv computer science archive if the pool is still short. By default it uses a 3-day window across all sources, scores the full candidate pool with topic-aware ranking, applies a stronger final reranking pass, and produces a polished reading list plus editor's picks.

> A tasteful daily radar for serious AI literature scanning.

## Highlights

- Finds newly added PubMed papers using the article `edat` window.
- Uses a staged candidate ladder: whitelisted journals first, then `MEDLINE[sb]` up to 50 total, then bioRxiv up to 80 total, then arXiv `cs` up to 100 total.
- Scores the full candidate pool with OpenAI across topic relevance, impact, rigor, interestingness, `awe_factor`, and `surprise_factor`.
- Uses a stronger second OpenAI pass to rerank the final shortlist.
- Keeps non-LLM topics on-track with topic-aware filtering and editor picks.
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
- `post_to_slack.py`: optional Slack delivery via Incoming Webhook
- `journal_whitelist_top40.txt`: curated journal whitelist
- `output/YYYY-MM-DD/`: generated daily Markdown and JSON files
- `data/pubmed_digest.sqlite3`: local incremental state

## Quick Start

Create a local `.env` file:

```bash
cat > .env <<'EOF'
OPENAI_API_KEY="your-openai-key"
NCBI_API_KEY="your-ncbi-key"
NCBI_EMAIL="you@example.com"
EOF
```

Then run the daily workflow:

```bash
./run_daily.sh
```

The scripts automatically load `.env` from the repository root. That file is ignored by git.

## Changing Topics

The easiest way to change topics is with `--topic` or the `TOPIC` environment variable.

Built-in presets:

- `llm`
- `medical-ai`
- `bioinformatics`
- `neuroscience`
- `nlp`

Examples:

```bash
python pubmed_digest.py --topic neuroscience
```

```bash
TOPIC=bioinformatics ./run_daily.sh
```

If you want a fully custom search, put your PubMed query in a text file and pass:

```bash
python pubmed_digest.py --topic-file topics/my_topic.txt
```

The daily runner supports the same pattern:

```bash
TOPIC_FILE=topics/spatial_transcriptomics.txt ./run_daily.sh
```

You can also change the default 3-day window without editing code:

```bash
DAYS_BACK=7 ./run_daily.sh
```

or:

```bash
PUBMED_DAYS_BACK=7 python pubmed_digest.py --topic bioinformatics
```

Or override everything directly:

```bash
python pubmed_digest.py --query '"spatial transcriptomics"[Title/Abstract] AND "foundation model"[Title/Abstract]'
```

## Slack Delivery

If `SLACK_WEBHOOK_URL` is present in `.env`, `./run_daily.sh` will post the finished digest to Slack automatically after generating `digest.md` and `editor-picks.md`.

You can also post an existing day's output manually:

```bash
python post_to_slack.py --date 2026-04-16
```

## How It Works

1. Search PubMed for recent papers matching the chosen topic over the default 3-day window.
2. Fill a candidate pool from the journal whitelist first.
3. If the pool is still below 50, search `MEDLINE[sb]`.
4. If the pool is still below 80, add bioRxiv candidates.
5. If the pool is still below 100, add arXiv `cs` candidates.
6. Fetch summaries, abstracts, and PMC full text when available.
7. Score the full candidate pool with a fast OpenAI model using topic-aware relevance.
8. Rerank the final shortlist with a stronger OpenAI model.
9. Select editor's picks from the same topic-aware pool.
10. Write:
   - a full digest
   - a machine-readable JSON export
   - a separate editor's picks summary

## Terminal Usage

Run the full workflow:

```bash
./run_daily.sh
```

Run the main digest only:

```bash
python pubmed_digest.py \
  --days-back 3 \
  --topic llm \
  --candidate-pool-size 100 \
  --retmax 10 \
  --model gpt-5.4-mini \
  --final-model gpt-5.4 \
  --journal-whitelist journal_whitelist_top40.txt
```

Run editor's picks only:

```bash
python editor_picks_from_pool.py
```

## Important Flags

- `--query`: override the default PubMed query
- `--topic`: switch to a built-in topic preset
- `--topic-file`: load a custom query from a text file
- `--days-back`: search N recent days across PubMed, bioRxiv, and arXiv; default is `PUBMED_DAYS_BACK` or `3`
- `--candidate-pool-size`: build up to this many candidates before ranking
- `--retmax`: number of final reranked papers to include in the digest
- `--model`: fast first-pass scoring model for the full pool; default is `gpt-5.4-mini`
- `--final-model`: stronger editorial reranking model for the shortlist
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
0 7 * * * cd /path/to/pubmed && ./run_daily.sh >> output/cron.log 2>&1
```

That runs every day at 7:00 AM in the machine's local time zone.

## Notes

- PubMed does not guarantee full paper text for every record. The pipeline uses PMC full text when available and falls back to abstract-only ranking otherwise.
- Topic presets are designed to be easy to switch, but you can always tighten them further with `--topic-file` or `--query` for a narrower domain.
- The preprint stages are opportunistic. If bioRxiv or arXiv rate-limit a run, the pipeline continues instead of failing the entire digest.
- Secrets stay local in `.env`; generated outputs and local state are ignored by git.
