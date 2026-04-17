#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

from pubmed_digest import ROOT, daily_output_dir, load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post today's digest to Slack via Incoming Webhook.")
    parser.add_argument(
        "--date",
        help="Date folder to post in YYYY-MM-DD format. Defaults to today.",
    )
    return parser.parse_args()


def format_pick_line(label: str, pick: dict, lookup: dict[str, dict]) -> str:
    paper = lookup.get(pick["paper_id"], {})
    entry_url = paper.get("entry_url")
    title = pick["title"]
    reason = pick.get("reason", "").strip()
    if len(reason) > 180:
        reason = reason[:177].rstrip() + "..."
    if entry_url:
        headline = f"*{label}:* <{entry_url}|{title}>"
    else:
        headline = f"*{label}:* {title}"
    if reason:
        return f"{headline}\n_{reason}_"
    return headline


def build_payload(digest_payload: dict, picks_payload: dict, run_date: str) -> dict:
    records = digest_payload.get("records", [])
    top_records = records[:3]
    topic = digest_payload.get("topic", "llm")
    search_metadata = digest_payload.get("search_metadata", {})
    papers = picks_payload.get("pool", [])
    lookup = {paper["paper_id"]: paper for paper in papers}
    picks = picks_payload.get("picks", {})

    summary_lines = [
        f"*PubMed Signal*  {run_date}",
        f"*Topic:* `{topic}`   *Window:* last {digest_payload.get('days_back', 'n/a')} day(s)",
        f"*Candidates scored:* {search_metadata.get('papers_fetched', 'n/a')}   *Final picks:* {len(records)}",
    ]

    top_lines = []
    for index, record in enumerate(top_records, start=1):
        paper = record["paper"]
        analysis = record["analysis"]
        journal = paper.get("journal", "Unknown journal")
        score = analysis.get("overall_recommendation_score", "n/a")
        label = analysis.get("recommendation_label", "unscored")
        why = analysis.get("why_it_matters", [])
        hook = why[0] if why else analysis.get("one_paragraph_summary", "")
        hook = hook.strip()
        if len(hook) > 180:
            hook = hook[:177].rstrip() + "..."
        top_lines.append(
            f"*{index}. <{paper['entry_url']}|{paper['title']}>*\n"
            f"_{journal}_  |  score *{score}*  |  {label}\n"
            f"{hook}"
        )

    pick_lines = []
    if "best_theoretical" in picks:
        pick_lines.append(format_pick_line("Theory", picks["best_theoretical"], lookup))
    if "best_methods" in picks:
        pick_lines.append(format_pick_line("Methods", picks["best_methods"], lookup))
    if "best_application" in picks:
        pick_lines.append(format_pick_line("Application", picks["best_application"], lookup))
    if "most_fun" in picks:
        pick_lines.append(format_pick_line("Fun / Easy Read", picks["most_fun"], lookup))

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "PubMed Signal", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)}},
        {"type": "divider"},
    ]
    if top_lines:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Top papers*\n\n" + "\n\n".join(top_lines)},
            }
        )
        blocks.append({"type": "divider"})
    if pick_lines:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Editor's picks*\n" + "\n".join(f"• {line}" for line in pick_lines)},
            }
        )
    if records:
        digest_path = f"output/{run_date}/digest.md"
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Full write-up saved locally in `{digest_path}`",
                    }
                ],
            }
        )
    return {"text": f"PubMed Signal for {run_date}", "blocks": blocks}


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL is not set; skipping Slack post.")
        return 0

    run_date = args.date or dt.date.today().isoformat()
    run_dir = ROOT / "output" / run_date
    if not run_dir.exists():
        raise SystemExit(f"Output folder not found for {run_date}: {run_dir}")

    digest_payload = json.loads((run_dir / "digest.json").read_text(encoding="utf-8"))
    picks_payload = json.loads((run_dir / "editor-picks.json").read_text(encoding="utf-8"))
    payload = build_payload(digest_payload, picks_payload, run_date)

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
