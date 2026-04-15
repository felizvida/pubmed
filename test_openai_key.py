#!/usr/bin/env python3
from pathlib import Path
import os
import sys

from openai import OpenAI


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def main() -> int:
    load_dotenv(Path("/Users/liux17/codex/pubmed/.env"))
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    try:
        response = client.responses.create(
            model="gpt-5.4-nano",
            reasoning={"effort": "low"},
            input="Reply with exactly: OK",
        )
    except Exception as exc:  # noqa: BLE001
        print("API_ERROR")
        print(type(exc).__name__)
        print(str(exc))
        return 1

    print("API_OK")
    print((getattr(response, "output_text", "") or "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
