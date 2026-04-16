#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

from openai import OpenAI

from pubmed_digest import (
    DEFAULT_DAYS_BACK,
    build_candidate_pmids,
    daily_output_dir,
    extract_json_object,
    extract_response_text,
    fetch_biorxiv_entry_map,
    fetch_arxiv_entry_map,
    fetch_pubmed_article_xml,
    fetch_summaries,
    init_db,
    load_dotenv,
    paper_from_arxiv_entry,
    paper_from_biorxiv_entry,
    paper_from_summary,
    parse_abstract,
    resolve_query,
    text_matches_topic,
)


ROOT = Path(__file__).resolve().parent
WHITELIST = ROOT / "journal_whitelist_top40.txt"
FINAL_MODEL = os.getenv("OPENAI_FINAL_MODEL", "gpt-5.4")


def main() -> int:
    load_dotenv(ROOT / ".env")
    conn = init_db()
    topic_file = Path(os.environ["PUBMED_TOPIC_FILE"]).expanduser() if os.getenv("PUBMED_TOPIC_FILE") else None
    query, topic_label = resolve_query(os.getenv("PUBMED_TOPIC", "llm"), os.getenv("PUBMED_QUERY"), topic_file)

    candidate_ids, metadata = build_candidate_pmids(
        conn=conn,
        query=query,
        topic_label=topic_label,
        days_back=DEFAULT_DAYS_BACK,
        candidate_pool_size=100,
        journal_whitelist_path=WHITELIST,
    )
    pubmed_ids = [item.split(":", 1)[1] for item in candidate_ids if item.startswith("pubmed:")]
    summaries = fetch_summaries(pubmed_ids)
    biorxiv_entries = fetch_biorxiv_entry_map(days_back=DEFAULT_DAYS_BACK, retmax=300, topic_label=topic_label, query=query)
    arxiv_entries = fetch_arxiv_entry_map(days_back=DEFAULT_DAYS_BACK, retmax=300, topic_label=topic_label, query=query)

    pool = []
    for candidate_id in candidate_ids:
        if candidate_id.startswith("pubmed:"):
            pmid = candidate_id.split(":", 1)[1]
            summary = summaries.get(pmid)
            if not summary:
                continue
            try:
                paper = paper_from_summary(pmid, summary, full_text_limit=12000)
            except Exception:
                try:
                    abstract = parse_abstract(fetch_pubmed_article_xml(pmid))
                except Exception:
                    abstract = ""
                journal = summary.get("fulljournalname", summary.get("source", "")).strip()
                title = summary.get("title", "").strip()
                pubdate = summary.get("pubdate", "").strip()
                authors = [author.get("name", "").strip() for author in summary.get("authors", []) if author.get("name")]
                pool.append(
                    {
                        "paper_id": pmid,
                        "source_db": "pubmed",
                        "title": title,
                        "journal": journal,
                        "pubdate": pubdate,
                        "authors": authors[:6],
                        "abstract": abstract[:5000],
                        "content_excerpt": abstract[:6000],
                        "content_source": "abstract_only",
                        "entry_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "link_label": "PubMed",
                    }
                )
                continue
            pool.append(
                {
                    "paper_id": paper.paper_id,
                    "source_db": paper.source_db,
                    "title": paper.title,
                    "journal": paper.journal,
                    "pubdate": paper.pubdate,
                    "authors": paper.authors[:6],
                    "abstract": paper.abstract[:5000],
                    "content_excerpt": (paper.full_text or paper.abstract)[:6000],
                    "content_source": paper.source,
                    "entry_url": paper.entry_url,
                    "link_label": paper.link_label,
                }
            )
        else:
            source_db, external_id = candidate_id.split(":", 1)
            if source_db == "biorxiv":
                entry = biorxiv_entries.get(external_id)
                if not entry:
                    continue
                paper = paper_from_biorxiv_entry(entry)
            else:
                entry = arxiv_entries.get(external_id)
                if not entry:
                    continue
                paper = paper_from_arxiv_entry(entry)
            pool.append(
                {
                    "paper_id": paper.paper_id,
                    "source_db": paper.source_db,
                    "title": paper.title,
                    "journal": paper.journal,
                    "pubdate": paper.pubdate,
                    "authors": paper.authors[:6],
                    "abstract": paper.abstract[:5000],
                    "content_excerpt": paper.abstract[:6000],
                    "content_source": paper.source,
                    "entry_url": paper.entry_url,
                    "link_label": paper.link_label,
                }
            )

    filtered_pool = [
        paper
        for paper in pool
        if text_matches_topic(f"{paper.get('title', '')}\n{paper.get('abstract', '')}", topic_label, query)
    ]
    if filtered_pool:
        pool = filtered_pool

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    instructions = textwrap.dedent(
        """
        You are selecting three editor's picks from a candidate pool of topic-specific research papers.
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
        - The chosen topic is: TOPIC_LABEL.
        - Only select papers that are genuinely central to the chosen topic.
        - Do not choose generic AI/ML papers unless the topic connection is explicit and substantial.
        - best_theoretical: strongest conceptual or methodological novelty, scientific depth, benchmark or modeling contribution
        - best_application: highest likely practical value, deployment relevance, workflow or clinical impact
        - most_fun: most delightfully weird, unexpected, charming, or conversation-starting paper while still being legitimate work
        """
    ).replace("TOPIC_LABEL", topic_label).strip()
    prompt = "Candidate pool:\n" + json.dumps({"search_metadata": metadata, "papers": pool}, ensure_ascii=True)
    response = client.responses.create(
        model=FINAL_MODEL,
        reasoning={"effort": "medium"},
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
