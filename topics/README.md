Put one custom PubMed query per `.txt` file in this folder.

Examples:

- `python pubmed_digest.py --topic-file topics/spatial_transcriptomics.txt`
- `TOPIC_FILE=topics/spatial_transcriptomics.txt ./run_daily.sh`

The file should contain plain PubMed query text, for example:

```text
"spatial transcriptomics"[Title/Abstract]
AND
("foundation model"[Title/Abstract] OR "large language model"[Title/Abstract])
```

