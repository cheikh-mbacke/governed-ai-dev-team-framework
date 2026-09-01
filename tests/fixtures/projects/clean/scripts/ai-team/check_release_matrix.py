#!/usr/bin/env python3
"""Verify pyproject.toml has a current entry in RELEASE_MATRIX."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC_ROOT = ROOT / "src"
if SRC_ROOT.is_dir() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from distribution.installer.version_policy import validate_release_matrix  # noqa: E402


def main() -> int:
    errors = validate_release_matrix(ROOT)
    if not errors:
        print("Release matrix alignment: OK")
        return 0
    for message in errors:
        print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
