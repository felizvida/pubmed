#!/usr/bin/env python3
"""
Daily PubMed digest for newly indexed LLM-related papers.

The script:
1. Searches PubMed for recent LLM-related additions.
2. Pulls metadata, abstract text, and PMC full text when available.
3. Uses the OpenAI Responses API to score papers for impact and interestingness.
4. Writes a Markdown digest and a machine-readable JSON export.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from openai import OpenAI


DEFAULT_QUERY = textwrap.dedent(
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

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
DB_PATH = DATA_DIR / "pubmed_digest.sqlite3"
REQUEST_TIMEOUT = 60
MAX_HTTP_RETRIES = 4


@dataclass
class Paper:
    pmid: str
    title: str
    authors: list[str]
    journal: str
    pubdate: str
    doi: str | None
    pmcid: str | None
    abstract: str
    full_text: str
    source: str
    pubmed_url: str
    pmc_url: str | None


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def http_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "pubmed-digest/0.1"})
    with open_with_retry(request) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_text(url: str, params: dict[str, Any]) -> str:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "pubmed-digest/0.1"})
    with open_with_retry(request) as response:
        return response.read().decode("utf-8", errors="replace")


def open_with_retry(request: urllib.request.Request):
    for attempt in range(MAX_HTTP_RETRIES):
        try:
            return urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == MAX_HTTP_RETRIES - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 1.5 * (2**attempt)
            time.sleep(delay)
        except urllib.error.URLError:
            if attempt == MAX_HTTP_RETRIES - 1:
                raise
            time.sleep(1.0 * (2**attempt))
    raise RuntimeError("unreachable retry state")


def ncbi_params() -> dict[str, str]:
    params: dict[str, str] = {"retmode": "json"}
    api_key = os.getenv("NCBI_API_KEY")
    email = os.getenv("NCBI_EMAIL")
    tool_name = os.getenv("NCBI_TOOL", "pubmed-digest")
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email
    if tool_name:
        params["tool"] = tool_name
    return params


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def init_db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_papers (
            pmid TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_digest_path TEXT
        )
        """
    )
    conn.commit()
    return conn


def search_pubmed(query: str, days_back: int, retmax: int) -> list[str]:
    params = {
        **ncbi_params(),
        "db": "pubmed",
        "term": query,
        "sort": "pub date",
        "reldate": str(days_back),
        "datetype": "edat",
        "retmax": str(retmax),
    }
    payload = http_get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params)
    return payload.get("esearchresult", {}).get("idlist", [])


def fetch_summaries(pmids: list[str]) -> dict[str, dict[str, Any]]:
    if not pmids:
        return {}
    params = {
        **ncbi_params(),
        "db": "pubmed",
        "id": ",".join(pmids),
    }
    payload = http_get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", params)
    result = payload.get("result", {})
    return {pmid: result[pmid] for pmid in pmids if pmid in result}


def fetch_pubmed_article_xml(pmid: str) -> ET.Element:
    params = {
        **ncbi_params(),
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
    }
    text = http_get_text("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params)
    return ET.fromstring(text)


def fetch_pmc_article_xml(pmcid: str) -> ET.Element:
    params = {
        **ncbi_params(),
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml",
    }
    text = http_get_text("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params)
    return ET.fromstring(text)


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_abstract(pubmed_root: ET.Element) -> str:
    sections: list[str] = []
    for abstract in pubmed_root.findall(".//Abstract"):
        for elem in abstract.findall("./AbstractText"):
            label = elem.attrib.get("Label")
            text = collapse_whitespace("".join(elem.itertext()))
            if not text:
                continue
            sections.append(f"{label}: {text}" if label else text)
    return "\n\n".join(sections)


def parse_pmc_full_text(pmc_root: ET.Element, char_limit: int) -> str:
    body = pmc_root.find(".//body")
    if body is None:
        return ""

    sections: list[str] = []
    for sec in body.findall(".//sec"):
        title_elem = sec.find("./title")
        title = collapse_whitespace("".join(title_elem.itertext())) if title_elem is not None else ""
        paragraphs = []
        for paragraph in sec.findall("./p"):
            text = collapse_whitespace("".join(paragraph.itertext()))
            if text:
                paragraphs.append(text)
        if paragraphs:
            joined = "\n\n".join(paragraphs)
            sections.append(f"{title}\n{joined}" if title else joined)

    if not sections:
        sections = [
            collapse_whitespace("".join(p.itertext()))
            for p in body.findall(".//p")
            if collapse_whitespace("".join(p.itertext()))
        ]

    text = "\n\n".join(sections)
    return text[:char_limit]


def paper_from_summary(pmid: str, summary: dict[str, Any], full_text_limit: int) -> Paper:
    pubmed_root = fetch_pubmed_article_xml(pmid)
    abstract = parse_abstract(pubmed_root)

    article_ids = {item.get("idtype"): item.get("value") for item in summary.get("articleids", []) if item.get("idtype")}
    pmcid = article_ids.get("pmc")
    full_text = ""
    source = "abstract_only"
    pmc_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None

    if pmcid:
        try:
            pmc_root = fetch_pmc_article_xml(pmcid)
            full_text = parse_pmc_full_text(pmc_root, full_text_limit)
            if full_text:
                source = "pmc_full_text"
        except (urllib.error.URLError, ET.ParseError):
            full_text = ""

    authors = [author.get("name", "").strip() for author in summary.get("authors", []) if author.get("name")]
    return Paper(
        pmid=pmid,
        title=collapse_whitespace(summary.get("title", "")),
        authors=authors,
        journal=collapse_whitespace(summary.get("fulljournalname", summary.get("source", ""))),
        pubdate=collapse_whitespace(summary.get("pubdate", "")),
        doi=article_ids.get("doi"),
        pmcid=pmcid,
        abstract=abstract,
        full_text=full_text,
        source=source,
        pubmed_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        pmc_url=pmc_url,
    )


def fetch_new_papers(
    conn: sqlite3.Connection,
    query: str,
    days_back: int,
    retmax: int,
    full_text_limit: int,
) -> list[Paper]:
    pmids = search_pubmed(query, days_back, retmax)
    if not pmids:
        return []

    seen = {
        row[0]
        for row in conn.execute("SELECT pmid FROM seen_papers WHERE pmid IN (%s)" % ",".join("?" for _ in pmids), pmids)
    } if pmids else set()
    new_pmids = [pmid for pmid in pmids if pmid not in seen]
    summaries = fetch_summaries(new_pmids)

    papers = []
    for pmid in new_pmids:
        summary = summaries.get(pmid)
        if not summary:
            continue
        try:
            papers.append(paper_from_summary(pmid, summary, full_text_limit))
            time.sleep(0.34)
        except (urllib.error.URLError, ET.ParseError) as exc:
            print(f"warning: failed to fetch PMID {pmid}: {exc}", file=sys.stderr)
    return papers


def extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()
    fragments: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                fragments.append(content["text"])
    return "\n".join(fragments).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("model did not return JSON")
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("unterminated JSON object")


def build_analysis_prompt(paper: Paper) -> str:
    content = paper.full_text or paper.abstract
    if not content:
        content = "No abstract or full text available."
    authors = ", ".join(paper.authors[:12]) if paper.authors else "Unknown"
    return textwrap.dedent(
        f"""
        Evaluate this newly indexed PubMed paper for an LLM reading digest.

        Title: {paper.title}
        PMID: {paper.pmid}
        Journal: {paper.journal}
        Publication date: {paper.pubdate}
        Authors: {authors}
        DOI: {paper.doi or "N/A"}
        Content source: {paper.source}

        Paper text:
        {content[:120000]}
        """
    ).strip()


def analyze_paper(paper: Paper, client: OpenAI, model: str) -> dict[str, Any]:
    prompt = build_analysis_prompt(paper)
    instructions = textwrap.dedent(
        """
        You are scoring biomedical papers for a daily LLM reading digest.
        Return exactly one JSON object and no surrounding markdown.

        Required schema:
        {
          "llm_relevance": 0-10 number,
          "impact_score": 0-10 number,
          "interestingness_score": 0-10 number,
          "awe_factor": 0-10 number,
          "surprise_factor": 0-10 number,
          "rigor_score": 0-10 number,
          "overall_recommendation_score": 0-100 integer,
          "recommendation_label": "must-read" | "worth-reading" | "skim" | "skip",
          "one_paragraph_summary": string,
          "why_it_matters": [string, string, ...],
          "concerns": [string, string, ...],
          "target_reader": string
        }

        Scoring guidance:
        - Prefer practical or scientifically important LLM work.
        - Reward novelty, study quality, likely influence, and genuinely useful insights.
        - Use awe_factor for work that feels especially impressive, ambitious, elegant, or field-shifting.
        - Use surprise_factor for unexpected findings, unusual applications, counterintuitive results, or clever combinations.
        - Penalize hype, weak evaluation, vague methods, or marginal relevance to LLMs.
        """
    ).strip()

    response = client.responses.create(
        model=model,
        reasoning={"effort": "low"},
        instructions=instructions,
        input=prompt,
    )
    text = getattr(response, "output_text", "") or extract_response_text(response.model_dump())
    parsed = extract_json_object(text)
    parsed["model"] = model
    return parsed


def analyze_papers(papers: list[Paper], api_key: str | None, model: str) -> list[dict[str, Any]]:
    results = []
    client = OpenAI(api_key=api_key) if api_key else None
    for paper in papers:
        analysis: dict[str, Any]
        if api_key:
            try:
                assert client is not None
                analysis = analyze_paper(paper, client, model)
            except Exception as exc:  # noqa: BLE001
                analysis = {
                    "error": str(exc),
                    "recommendation_label": "unscored",
                    "overall_recommendation_score": 0,
                    "one_paragraph_summary": "OpenAI scoring failed for this paper.",
                    "why_it_matters": [],
                    "concerns": [str(exc)],
                    "target_reader": "Unknown",
                }
        else:
            analysis = {
                "recommendation_label": "unscored",
                "overall_recommendation_score": 0,
                "one_paragraph_summary": "No OPENAI_API_KEY provided, so this paper was collected but not ranked.",
                "why_it_matters": [],
                "concerns": ["Set OPENAI_API_KEY to enable scoring and digest ranking."],
                "target_reader": "Unknown",
            }
        results.append({"paper": asdict(paper), "analysis": analysis})
    results.sort(key=lambda item: item["analysis"].get("overall_recommendation_score", 0), reverse=True)
    return results


def write_outputs(records: list[dict[str, Any]], query: str, days_back: int) -> tuple[Path, Path]:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    markdown_path = OUTPUT_DIR / f"pubmed-digest-{timestamp}.md"
    json_path = OUTPUT_DIR / f"pubmed-digest-{timestamp}.json"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "days_back": days_back,
                "query": query,
                "records": records,
            },
            handle,
            indent=2,
        )

    lines = [
        f"# PubMed LLM Digest ({dt.datetime.now().strftime('%Y-%m-%d')})",
        "",
        f"- Query window: last {days_back} day(s)",
        f"- Papers found: {len(records)}",
        "",
        "## Recommended Reading",
        "",
    ]

    if not records:
        lines.append("No new papers matched the query window.")
    for index, record in enumerate(records, start=1):
        paper = record["paper"]
        analysis = record["analysis"]
        authors = ", ".join(paper["authors"][:8]) if paper["authors"] else "Unknown authors"
        score = analysis.get("overall_recommendation_score", 0)
        label = analysis.get("recommendation_label", "unscored")
        lines.extend(
            [
                f"### {index}. {paper['title']}",
                "",
                f"- Score: {score} ({label})",
                f"- Subscores: impact {analysis.get('impact_score', 'n/a')}/10, interestingness {analysis.get('interestingness_score', 'n/a')}/10, awe {analysis.get('awe_factor', 'n/a')}/10, surprise {analysis.get('surprise_factor', 'n/a')}/10, rigor {analysis.get('rigor_score', 'n/a')}/10, relevance {analysis.get('llm_relevance', 'n/a')}/10",
                f"- Journal: {paper['journal']}",
                f"- Date: {paper['pubdate']}",
                f"- Authors: {authors}",
                f"- PMID: [{paper['pmid']}]({paper['pubmed_url']})",
            ]
        )
        if paper.get("pmc_url"):
            lines.append(f"- Full text: [PMC]({paper['pmc_url']})")
        if paper.get("doi"):
            lines.append(f"- DOI: {paper['doi']}")
        lines.extend(
            [
                "",
                analysis.get("one_paragraph_summary", "No summary available."),
                "",
                "**Why it matters**",
            ]
        )
        for item in analysis.get("why_it_matters", [])[:4]:
            lines.append(f"- {item}")
        if not analysis.get("why_it_matters"):
            lines.append("- No rationale available.")
        lines.append("")
        lines.append("**Concerns**")
        for item in analysis.get("concerns", [])[:4]:
            lines.append(f"- {item}")
        if not analysis.get("concerns"):
            lines.append("- No major concerns flagged.")
        lines.append("")

    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return markdown_path, json_path


def mark_seen(conn: sqlite3.Connection, records: list[dict[str, Any]], digest_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = [
        (record["paper"]["pmid"], now, str(digest_path))
        for record in records
        if not record["analysis"].get("error")
    ]
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO seen_papers (pmid, first_seen_at, last_digest_path)
        VALUES (?, ?, ?)
        ON CONFLICT(pmid) DO UPDATE SET last_digest_path = excluded.last_digest_path
        """,
        rows,
    )
    conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days-back", type=int, default=1, help="Search the last N days of PubMed additions.")
    parser.add_argument("--retmax", type=int, default=25, help="Maximum number of PubMed hits to inspect per run.")
    parser.add_argument(
        "--query",
        default=os.getenv("PUBMED_QUERY", DEFAULT_QUERY),
        help="PubMed query string. Defaults to an LLM-focused query.",
    )
    parser.add_argument(
        "--full-text-char-limit",
        type=int,
        default=120000,
        help="Maximum number of full-text characters to send to the LLM.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for scoring.")
    parser.add_argument(
        "--mark-seen-without-scoring",
        action="store_true",
        help="Persist seen PMIDs even when OPENAI_API_KEY is missing.",
    )
    parser.add_argument(
        "--mark-seen-on-error",
        action="store_true",
        help="Persist papers even when OpenAI scoring fails.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    conn = init_db()
    papers = fetch_new_papers(
        conn=conn,
        query=args.query,
        days_back=args.days_back,
        retmax=args.retmax,
        full_text_limit=args.full_text_char_limit,
    )
    if not papers:
        print("No new matching PubMed papers found.")
        return 0

    api_key = os.getenv("OPENAI_API_KEY")
    records = analyze_papers(papers, api_key=api_key, model=args.model)
    markdown_path, json_path = write_outputs(records, query=args.query, days_back=args.days_back)

    if args.mark_seen_on_error:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        rows = [(record["paper"]["pmid"], now, str(markdown_path)) for record in records]
        conn.executemany(
            """
            INSERT INTO seen_papers (pmid, first_seen_at, last_digest_path)
            VALUES (?, ?, ?)
            ON CONFLICT(pmid) DO UPDATE SET last_digest_path = excluded.last_digest_path
            """,
            rows,
        )
        conn.commit()
    elif api_key or args.mark_seen_without_scoring:
        mark_seen(conn, records, markdown_path)

    print(f"Wrote Markdown digest to {markdown_path}")
    print(f"Wrote JSON export to {json_path}")
    if not api_key:
        print("OPENAI_API_KEY is not set, so papers were collected but not ranked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
