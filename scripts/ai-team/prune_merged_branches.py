#!/usr/bin/env python3
"""List or delete remote branches already merged into main (governed prefixes only)."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GOVERNED_BRANCH_RE = re.compile(r"^(wu|ai-run|integration|hotfix)/")
PROTECTED = frozenset({"main", "master"})
MAINTENANCE_PREFIX = "release/"


def git(*args: str, root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def merged_governed_remote_branches(root: Path = ROOT) -> list[str]:
    git("fetch", "origin", "main", "--prune", root=root)
    names: list[str] = []
    for line in git("branch", "-r", "--merged", "origin/main", root=root).splitlines():
        ref = line.strip()
        if not ref.startswith("origin/"):
            continue
        name = ref.removeprefix("origin/")
        if name in PROTECTED or name.startswith(MAINTENANCE_PREFIX):
            continue
        if not GOVERNED_BRANCH_RE.match(name):
            continue
        names.append(name)
    return sorted(set(names))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete merged branches (default is dry-run)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        branches = merged_governed_remote_branches()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not branches:
        print("No governed remote branches merged into origin/main.")
        return 0

    if not args.apply:
        print("Dry-run — merged governed branches that would be deleted:")
        for name in branches:
            print(f"  origin/{name}")
        print("\nRe-run with --apply to delete them.")
        return 0

    failures = 0
    for name in branches:
        completed = subprocess.run(
            ["git", "push", "origin", "--delete", name],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode == 0:
            print(f"Deleted origin/{name}")
        else:
            failures += 1
            detail = (completed.stderr or completed.stdout).strip()
            print(f"Failed to delete origin/{name}: {detail}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
