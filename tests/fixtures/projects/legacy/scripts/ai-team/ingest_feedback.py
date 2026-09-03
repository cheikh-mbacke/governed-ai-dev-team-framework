#!/usr/bin/env python3
"""Ingest consented Feedback Exports into the framework learning inbox."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker

from governed_ai.learning.aggregate import write_aggregate

INBOX = _REPO_ROOT / "learning" / "inbox"
SCHEMA = (
    _REPO_ROOT
    / "distribution"
    / "payload"
    / ".ai-team"
    / "schemas"
    / "feedback-export.schema.json"
)


def ingest_document(document: dict, *, inbox: Path = INBOX) -> Path:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.path),
    )
    if errors:
        messages = []
        for error in errors:
            location = "/".join(map(str, error.path)) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ValueError("Invalid feedback payload: " + "; ".join(messages))

    export_id = document["export_id"]
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / f"{export_id}.json"
    if not target.is_file():
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    write_aggregate(inbox=inbox)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-file",
        type=Path,
        help="Read one Feedback Export JSON file (default: stdin)",
    )
    parser.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Skip refreshing learning/aggregate/latest.json",
    )
    args = parser.parse_args()
    if args.from_file:
        raw = args.from_file.read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    document = json.loads(raw)
    if not isinstance(document, dict):
        print("payload must be a JSON object", file=sys.stderr)
        return 1
    try:
        if args.no_aggregate:
            # Direct write without aggregate refresh (tests / batch ingest).
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            errors = sorted(
                Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                    document
                ),
                key=lambda error: list(error.path),
            )
            if errors:
                raise ValueError(
                    "Invalid feedback payload: "
                    + "; ".join(
                        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
                        for e in errors
                    )
                )
            INBOX.mkdir(parents=True, exist_ok=True)
            target = INBOX / f"{document['export_id']}.json"
            if not target.is_file():
                target.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            path = target
        else:
            path = ingest_document(document)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
