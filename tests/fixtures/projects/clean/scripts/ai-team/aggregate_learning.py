#!/usr/bin/env python3
"""Rebuild learning/aggregate/latest.json from learning/inbox exports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from governed_ai.learning.aggregate import write_aggregate

INBOX = _REPO_ROOT / "learning" / "inbox"
DEFAULT_OUTPUT = _REPO_ROOT / "learning" / "aggregate" / "latest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=INBOX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = write_aggregate(inbox=args.inbox, output=args.output)
    print(
        f"{result.index_path.as_posix()} "
        f"exports={result.export_count} observations={result.observation_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
