#!/usr/bin/env python3
"""Regenerate .ai-team/framework-version.json for the framework source repository."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from distribution.installer.record import LEGACY_VERSION_FILE  # noqa: E402
from distribution.installer.source_manifest import (  # noqa: E402
    build_source_manifest,
    write_source_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Framework source repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when committed framework-version.json is out of date",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest_path = root / LEGACY_VERSION_FILE

    if args.check:
        if not manifest_path.is_file():
            print(f"Missing {manifest_path.relative_to(root)}", file=sys.stderr)
            return 1
        committed = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = build_source_manifest(root)
        if committed != expected:
            print(
                f"{manifest_path.relative_to(root)} is out of date; "
                "run: python scripts/ai-team/sync_source_manifest.py",
                file=sys.stderr,
            )
            return 1
        print(
            f"OK {manifest_path.relative_to(root)} "
            f"(version {expected['version']}, {len(expected['managed_files'])} source paths)"
        )
        return 0

    path = write_source_manifest(root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(
        f"Wrote {path.relative_to(root)} "
        f"(version {payload['version']}, {len(payload['managed_files'])} source paths)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
