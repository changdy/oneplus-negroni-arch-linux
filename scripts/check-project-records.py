#!/usr/bin/env python3
"""Keep the curated conversation inventory and its delivery references usable."""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def check():
    path = PROJECT / "artifacts/project-audit-20261115/conversations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    seen = set()
    counts = {}
    for provider in ("codex", "cursor", "supplementary_research"):
        records = data[provider]
        counts[provider] = len(records)
        for record in records:
            key = (provider, record["id"])
            if key in seen or not record["disposition"]:
                raise RuntimeError(f"duplicate or unreviewed conversation: {key}")
            seen.add(key)
            doc = record.get("primary_doc")
            if doc and not (PROJECT / doc).is_file():
                raise RuntimeError(f"missing conversation destination: {doc}")
    for feature in ("camera", "nfc", "gnss", "desktop"):
        for name in (f"scripts/configure-{feature}.sh", f"scripts/verify-{feature}-image.py"):
            if not (PROJECT / name).is_file():
                raise RuntimeError(f"missing delivery entry: {name}")
    print("Conversation inventory checked:", counts)


if __name__ == "__main__":
    check()
