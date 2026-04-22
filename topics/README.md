Put one custom PubMed query per `.txt` file in this folder.

Examples:

- `python pubmed_digest.py --topic-file topics/spatial_transcriptomics.txt`
- `TOPIC_FILE=topics/spatial_transcriptomics.txt ./run_daily.sh`
- `DAYS_BACK=10 TOPIC_FILE=topics/spatial_transcriptomics.txt POST_TO_SLACK=0 ./run_daily.sh`

The file should contain plain PubMed query text, for example:

```text
"spatial transcriptomics"[Title/Abstract]
AND
("foundation model"[Title/Abstract] OR "large language model"[Title/Abstract])
```

Tips:

- Keep quoted phrases intact when they represent one concept, such as `"mass spectrometry"` or `"single-cell"`.
- If a topic is broad, start with a domain block and an AI block joined by `AND`.
- Use a topic file when you want a repeatable sharp query without editing code.
