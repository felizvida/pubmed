# PubMed Signal

![PubMed Signal banner](assets/banner.svg)

Journal-aware daily discovery and ranking for AI-related papers from PubMed, bioRxiv, and arXiv.

PubMed Signal is built for people who want a serious daily reading list instead of a noisy firehose. It starts with trusted journals, widens to `MEDLINE[sb]` only when needed, then reaches into bioRxiv and arXiv to fill the pool. It scores the candidate set with OpenAI, reranks the shortlist with a stronger model, and produces both a full digest and a compact set of editor's picks.

> A tasteful daily radar for research worth opening first.

## Why It Feels Different

- It is journal-first instead of preprint-first.
- It uses topic-aware ranking, so `bioinformatics`, `neuroscience`, `medical-ai`, or a custom query do not all get treated like generic LLM news.
- It keeps source lanes separate, so one noisy feed cannot crowd out the rest of the pool.
- It writes a digest for humans, JSON for automation, and editor's picks for fast scanning.
- It can post a polished briefing to Slack when you want delivery built in.

## What You Get

- A staged daily candidate ladder:
  - PubMed fills to `50`
  - bioRxiv fills the pool to `80`
  - arXiv fills the pool to `100`
- Full-pool scoring with topic relevance, impact, interestingness, rigor, `awe_factor`, and `surprise_factor`
- Editor's picks for:
  - theoretical research
  - methods / techniques / algorithmic improvement
  - impactful application
  - fun / humor / easy read
- Per-paper scores in the main digest
- Per-pick scores in editor's picks
- Incremental local state, so recurring runs do not keep resurfacing the same papers

## Quick Start

Create a local `.env` file:

```bash
cat > .env <<'EOF'
OPENAI_API_KEY="your-openai-key"
NCBI_API_KEY="your-ncbi-key"
NCBI_EMAIL="you@example.com"
EOF
```

Run the daily workflow:

```bash
./run_daily.sh
```

The scripts automatically load `.env` from the repository root. That file is ignored by git.

## Fast Examples

Run the default daily workflow:

```bash
./run_daily.sh
```

Run a 10-day bioinformatics pass:

```bash
DAYS_BACK=10 TOPIC=bioinformatics ./run_daily.sh
```

Run without posting to Slack:

```bash
POST_TO_SLACK=0 ./run_daily.sh
```

Run the main digest only:

```bash
python pubmed_digest.py \
  --days-back 10 \
  --topic bioinformatics \
  --candidate-pool-size 100 \
  --retmax 10 \
  --journal-whitelist journal_whitelist_top40.txt
```

Run editor's picks only:

```bash
python editor_picks_from_pool.py
```

Post an existing day to Slack:

```bash
python post_to_slack.py --date 2026-04-20
```

## Topics

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

For a custom topic, put your PubMed query in a text file:

```bash
python pubmed_digest.py --topic-file topics/spatial_transcriptomics.txt
```

or:

```bash
TOPIC_FILE=topics/spatial_transcriptomics.txt ./run_daily.sh
```

You can also override directly:

```bash
python pubmed_digest.py --query '"spatial transcriptomics"[Title/Abstract] AND "foundation model"[Title/Abstract]'
```

## How Selection Works

1. Search PubMed over the chosen window.
2. Fill the PubMed lane from the journal whitelist first.
3. If PubMed is still below `50`, add `MEDLINE[sb]` until PubMed reaches `50`.
4. If the combined pool is still below `80`, add bioRxiv until the pool reaches `80`.
5. If the combined pool is still below `100`, add arXiv `cs` until the pool reaches `100`.
6. Tighten any overfull source inside its own lane before selection.
7. Fetch metadata, abstracts, and PMC full text when available.
8. Score the full candidate pool with a lighter OpenAI model.
9. Rerank the final shortlist with a stronger OpenAI model.
10. Select editor's picks from the same topic-aware pool.

Example:

If PubMed yields `48`, bioRxiv can add up to `32` to bring the pool to `80`. If PubMed plus bioRxiv only reaches `32`, arXiv can add up to `68` to bring the pool to `100`.

## Scoring

Each paper is scored on:

- topic relevance
- impact
- interestingness
- rigor
- awe
- surprise

By default, the project queries the OpenAI Models API, prefers a lighter model for full-pool scoring, and prefers the flagship model for final editorial reranking if both are available.

## Output

Each normal run writes into:

- `output/YYYY-MM-DD/digest.md`
- `output/YYYY-MM-DD/digest.json`
- `output/YYYY-MM-DD/editor-picks.md`
- `output/YYYY-MM-DD/editor-picks.json`

For ad hoc experimental runs, you can point the scripts at a different output root; those runs are commonly kept outside the main daily folder structure.

`digest.md` is the full reading list.
`editor-picks.md` is the shorter human-friendly briefing.
The JSON files are useful for Slack, email, or downstream tooling.

## Slack Delivery

If `SLACK_WEBHOOK_URL` is set in `.env`, `run_daily.sh` can post the finished digest to Slack automatically.

To skip Slack for a given run:

```bash
POST_TO_SLACK=0 ./run_daily.sh
```

The Slack post includes:

- a short run summary
- top ranked papers
- editor's picks
- one-line reasons for each pick
- scores for both the main digest and the picks

## Repository Layout

- `pubmed_digest.py`: retrieval, scoring, reranking, and digest writing
- `editor_picks_from_pool.py`: editor's-picks selection from the daily candidate pool
- `post_to_slack.py`: Slack delivery formatter and sender
- `run_daily.sh`: one-command terminal runner
- `journal_whitelist_top40.txt`: curated journal whitelist
- `topics/`: example custom topic files
- `assets/`: GitHub-facing visuals
- `output/`: daily outputs
- `data/pubmed_digest.sqlite3`: local incremental state

## Important Flags

- `--query`: override the default PubMed query
- `--topic`: switch to a built-in topic preset
- `--topic-file`: load a custom query from a text file
- `--days-back`: search N recent days across PubMed, bioRxiv, and arXiv
- `--candidate-pool-size`: maximum pool size before ranking
- `--retmax`: number of final reranked papers in the digest
- `--model`: override the first-pass scoring model
- `--final-model`: override the final reranking model
- `--journal-whitelist`: newline-delimited whitelist file
- `--full-text-char-limit`: trim long PMC full text before scoring
- `--mark-seen-without-scoring`: persist PMIDs even when no OpenAI key is set
- `--mark-seen-on-error`: persist PMIDs even when OpenAI scoring fails

## Scheduling

Example cron entry:

```cron
0 7 * * * cd /path/to/pubmed && ./run_daily.sh >> output/cron.log 2>&1
```

That runs every day at 7:00 AM in the machine's local time zone.

## Notes

- PubMed does not guarantee full paper text for every record. The pipeline uses PMC full text when available and falls back to abstract-only ranking otherwise.
- Topic presets are meant to be easy to switch, but custom topic files are the best way to get very sharp domain-specific behavior.
- Preprint sources are opportunistic. If bioRxiv or arXiv are slow or flaky, the pipeline continues instead of failing the entire digest.
- Secrets stay local in `.env`; generated outputs and local state are ignored by git.
