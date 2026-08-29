#!/usr/bin/env python3
"""Regenerate frozen golden compile manifest (Document 13 Phase 4 §4.2)."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from adapters.cursor.compiler.compile import compile_manifest  # noqa: E402
from adapters.cursor.compiler.parity import build_golden_manifest  # noqa: E402

BUNDLE_V1 = ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
TEMPLATES = ROOT / "adapters" / "cursor" / "templates"
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "cursor-compile" / "golden-manifest.json"
PROFILE = {
    "project_id": "framework-renov",
    "primary_language": "python",
    "package_manager": "pip",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write tests/fixtures/cursor-compile/golden-manifest.json",
    )
    args = parser.parse_args()
    if not args.write:
        parser.error("pass --write to regenerate the golden manifest")

    with tempfile.TemporaryDirectory(prefix="cursor-golden-") as temp_dir:
        staging = Path(temp_dir)
        manifest = compile_manifest(
            BUNDLE_V1,
            staging,
            PROFILE,
            templates_root=TEMPLATES,
        )
        golden = build_golden_manifest(manifest)

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {GOLDEN_PATH} ({len(golden['artifacts'])} artefacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
