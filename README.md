# PubMed Signal

![PubMed Signal banner](assets/banner.svg)

Daily, journal-aware discovery and ranking of recent PubMed, bioRxiv, and arXiv papers on your chosen AI-related research topic.

This project builds a candidate pool from reputable journals, expands to `MEDLINE[sb]` only if needed, then reaches into bioRxiv and the arXiv computer science archive if the pool is still short. By default it uses a 3-day window across all sources, scores the full candidate pool with topic-aware ranking, queries your available OpenAI models, prefers the flagship model for the strongest pass and a lighter model for cheaper passes, and produces a polished reading list plus editor's picks.

> A tasteful daily radar for serious AI literature scanning.

## Highlights

- Finds newly added PubMed papers using the article `edat` window.
- Uses a staged candidate ladder with cumulative thresholds: PubMed fills to 50 total, then bioRxiv fills the pool to 80 total, then arXiv `cs` fills the pool to 100 total.
- Tightens an overfull source within its own lane before selection, so one noisy subgroup does not crowd out the rest of the pool.
- Scores the full candidate pool with OpenAI across topic relevance, impact, rigor, interestingness, `awe_factor`, and `surprise_factor`.
- Queries your available OpenAI models and chooses a flagship model for final ranking plus a lighter model for cheaper scoring by default.
- Keeps non-LLM topics on-track with topic-aware filtering and editor picks.
- Produces editor's picks for:
  - theoretical research
  - methods / techniques / algorithmic improvement
  - impactful application
  - fun / humor / easy read
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
2. Fill the PubMed lane from the journal whitelist first.
3. If PubMed is still below 50 total, add `MEDLINE[sb]` results until the PubMed lane reaches 50.
4. If the combined pool is still below 80 total, add bioRxiv results until the pool reaches 80.
5. If the combined pool is still below 100 total, add arXiv `cs` results until the pool reaches 100.
6. Fetch summaries, abstracts, and PMC full text when available.
7. Score the full candidate pool with a fast OpenAI model using topic-aware relevance.
8. Rerank the final shortlist with a stronger OpenAI model.
9. Select editor's picks from the same topic-aware pool.
10. Write:
   - a full digest
   - a machine-readable JSON export
   - a separate editor's picks summary

Example:
If whitelisted journals plus `MEDLINE[sb]` only produce 48 papers, bioRxiv can add up to 32 to bring the pool to 80. If the combined PubMed plus bioRxiv pool reaches only 32, arXiv can add up to 68 to bring the pool to 100.

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
- `--model`: first-pass scoring model for the full pool; if unset, the script queries available models and prefers `gpt-5.4-mini`
- `--final-model`: stronger editorial reranking model for the shortlist; if unset, the script queries available models and prefers `gpt-5.4`
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
- Stage thresholds are cumulative, not fixed per source. A source gets whatever slots remain before the next threshold, and if it returns more than that, the code tightens that source within its own allocation before selection.
- If `OPENAI_MODEL` and `OPENAI_FINAL_MODEL` are unset, the code asks OpenAI which models are available and picks a sensible default pair instead of assuming fixed names.
- Secrets stay local in `.env`; generated outputs and local state are ignored by git.
