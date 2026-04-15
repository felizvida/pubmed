#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

from openai import OpenAI

from pubmed_digest import (
    build_candidate_pmids,
    daily_output_dir,
    extract_json_object,
    extract_response_text,
    fetch_arxiv_entry_map,
    fetch_pubmed_article_xml,
    fetch_summaries,
    init_db,
    load_dotenv,
    parse_abstract,
)


ROOT = Path(__file__).resolve().parent
WHITELIST = ROOT / "journal_whitelist_top40.txt"


def main() -> int:
    load_dotenv(ROOT / ".env")
    conn = init_db()
    query = os.getenv("PUBMED_QUERY") or textwrap.dedent(
        """
        (
          "large language model"[Title/Abstract]
          OR "large language models"[Title/Abstract]
          OR LLM[Title/Abstract]
          OR GPT-4[Title/Abstract]
          OR GPT-4o[Title/Abstract]
          OR GPT-5[Title/Abstract]
          OR "foundation model"[Title/Abstract]
          OR "foundation models"[Title/Abstract]
          OR "generative AI"[Title/Abstract]
          OR "generative artificial intelligence"[Title/Abstract]
          OR "retrieval augmented generation"[Title/Abstract]
          OR RAG[Title/Abstract]
          OR "transformer model"[Title/Abstract]
          OR "transformer models"[Title/Abstract]
        )
        """
    ).strip()

    candidate_ids, metadata = build_candidate_pmids(
        conn=conn,
        query=query,
        days_back=365,
        candidate_pool_size=100,
        journal_whitelist_path=WHITELIST,
    )
    pubmed_ids = [item.split(":", 1)[1] for item in candidate_ids if item.startswith("pubmed:")]
    summaries = fetch_summaries(pubmed_ids)
    arxiv_entries = fetch_arxiv_entry_map(days_back=365, retmax=300)

    pool = []
    for candidate_id in candidate_ids:
        if candidate_id.startswith("pubmed:"):
            pmid = candidate_id.split(":", 1)[1]
            summary = summaries.get(pmid)
            if not summary:
                continue
            journal = summary.get("fulljournalname", summary.get("source", "")).strip()
            title = summary.get("title", "").strip()
            pubdate = summary.get("pubdate", "").strip()
            authors = [author.get("name", "").strip() for author in summary.get("authors", []) if author.get("name")]
            try:
                abstract = parse_abstract(fetch_pubmed_article_xml(pmid))
            except Exception:
                abstract = ""
            pool.append(
                {
                    "paper_id": pmid,
                    "source_db": "pubmed",
                    "title": title,
                    "journal": journal,
                    "pubdate": pubdate,
                    "authors": authors[:6],
                    "abstract": abstract[:2000],
                    "entry_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "link_label": "PubMed",
                }
            )
        else:
            arxiv_id = candidate_id.split(":", 1)[1]
            entry = arxiv_entries.get(arxiv_id)
            if not entry:
                continue
            pool.append(
                {
                    "paper_id": arxiv_id,
                    "source_db": "arxiv",
                    "title": entry["title"],
                    "journal": entry["journal"],
                    "pubdate": entry["pubdate"],
                    "authors": entry["authors"][:6],
                    "abstract": entry["abstract"][:2000],
                    "entry_url": entry["entry_url"],
                    "link_label": "arXiv",
                }
            )

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    instructions = textwrap.dedent(
        """
        You are selecting three editor's picks from a candidate pool of LLM-related research papers.
        Return exactly one JSON object and no markdown.

        Required schema:
        {
          "best_theoretical": {
            "paper_id": "string",
            "title": "string",
            "reason": "string"
          },
          "best_application": {
            "paper_id": "string",
            "title": "string",
            "reason": "string"
          },
          "most_fun": {
            "paper_id": "string",
            "title": "string",
            "reason": "string"
          }
        }

        Category guidance:
        - best_theoretical: strongest conceptual or methodological novelty, scientific depth, benchmark or modeling contribution
        - best_application: highest likely practical value, deployment relevance, workflow or clinical impact
        - most_fun: most delightfully weird, unexpected, charming, or conversation-starting paper while still being legitimate work
        """
    ).strip()
    prompt = "Candidate pool:\n" + json.dumps({"search_metadata": metadata, "papers": pool}, ensure_ascii=True)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
        reasoning={"effort": "low"},
        instructions=instructions,
        input=prompt,
    )
    text = getattr(response, "output_text", "") or extract_response_text(response.model_dump())
    picks = extract_json_object(text)
    run_dir = daily_output_dir()
    json_path = run_dir / "editor-picks.json"
    md_path = run_dir / "editor-picks.md"
    payload = {"search_metadata": metadata, "pool": pool, "picks": picks}
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lookup = {item["paper_id"]: item for item in pool}
    lines = [
        "# Editor's Picks",
        "",
        f"- Candidate pool target: {metadata.get('candidate_pool_size')}",
        "",
    ]
    sections = [
        ("Top Theoretical Pick", "best_theoretical"),
        ("Top Application Pick", "best_application"),
        ("Top Fun Pick", "most_fun"),
    ]
    for heading, key in sections:
        pick = picks[key]
        paper = lookup.get(pick["paper_id"], {})
        entry_url = paper.get("entry_url", "")
        link_label = paper.get("link_label", "Link")
        lines.extend(
            [
                f"## {heading}",
                "",
                f"**{pick['title']}**",
                "",
                f"- Source: {paper.get('source_db', 'unknown')}",
                f"- {link_label}: [{pick['paper_id']}]({entry_url})" if entry_url else f"- Identifier: {pick['paper_id']}",
                f"- Journal: {paper.get('journal', 'Unknown')}",
                f"- Date: {paper.get('pubdate', 'Unknown')}",
                "",
                pick["reason"],
                "",
            ]
        )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
