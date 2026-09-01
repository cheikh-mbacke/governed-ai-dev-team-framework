"""WU-P4-SHADOW-COMPILE — golden compile manifest tests."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.cursor.compiler.compile import compile_manifest
from adapters.cursor.compiler.parity import (
    GoldenManifest,
    build_golden_manifest,
    verify_golden_compile,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
TEMPLATES_ROOT = REPO_ROOT / "adapters" / "cursor" / "templates"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "cursor-compile" / "golden-manifest.json"
PROJECT_PROFILE = {
    "project_id": "framework-renov",
    "primary_language": "python",
    "package_manager": "pip",
}


def test_golden_manifest_documents_line_ending_policy() -> None:
    golden = GoldenManifest.load(GOLDEN_PATH)
    kinds = {entry.get("kind") for entry in golden.documented_differences}
    assert "line_endings" in kinds
    assert golden.bundle_version == "1.0.0"
    assert len(golden.artifacts) == 49


def test_compile_matches_frozen_golden_manifest(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    manifest = compile_manifest(
        BUNDLE_V1,
        staging,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    golden = GoldenManifest.load(GOLDEN_PATH)
    errors = verify_golden_compile(staging, golden)
    assert errors == [], "\n".join(errors)

    rebuilt = build_golden_manifest(manifest)
    assert rebuilt["artifacts"] == json.loads(GOLDEN_PATH.read_text())["artifacts"]
