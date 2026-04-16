# PubMed Signal

![PubMed Signal banner](assets/banner.svg)

Daily, journal-aware discovery and ranking of recent PubMed and arXiv papers about LLMs, foundation models, and adjacent AI methods.

This project builds a candidate pool from reputable journals, expands to `MEDLINE[sb]` only if needed, then reaches into the arXiv computer science archive if the pool is still short. By default it uses a 3-day window across all sources, scores the full candidate pool, applies a stronger final reranking pass, and produces a polished reading list plus editor's picks.

> A tasteful daily radar for serious AI literature scanning.

## Highlights

- Finds newly added PubMed papers using the article `edat` window.
- Uses a curated `top40` journal whitelist first, then falls back to `MEDLINE[sb]`, then arXiv `cs`, to fill a target candidate pool.
- Scores the full candidate pool with OpenAI across relevance, impact, rigor, interestingness, `awe_factor`, and `surprise_factor`.
- Uses a stronger second OpenAI pass to rerank the final shortlist.
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

Or override everything directly:

```bash
python pubmed_digest.py --query '"spatial transcriptomics"[Title/Abstract] AND "foundation model"[Title/Abstract]'
```

## How It Works

1. Search PubMed for recent LLM-related papers over the default 3-day window.
2. Fill a candidate pool from the journal whitelist first.
3. If the pool is still too small, search `MEDLINE[sb]` as a fallback.
4. If the pool is still too small, add arXiv `cs` candidates.
5. Fetch summaries, abstracts, and PMC full text when available.
6. Score the full candidate pool with a fast OpenAI model.
7. Rerank the final shortlist with a stronger OpenAI model.
8. Write:
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
  --model gpt-5.4-nano \
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
- `--days-back`: search N recent days across PubMed and arXiv; default is `3`
- `--candidate-pool-size`: build up to this many candidates before ranking
- `--retmax`: number of final reranked papers to include in the digest
- `--model`: fast first-pass scoring model for the full pool
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
- The default query is intentionally broad, but the journal-first retrieval strategy keeps the recommendation quality much higher than a raw PubMed scrape.
- Secrets stay local in `.env`; generated outputs and local state are ignored by git.
