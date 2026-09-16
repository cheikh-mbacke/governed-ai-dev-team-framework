"""Golden compile manifest tests for the Claude Code Adaptateur (mirrors Cursor's)."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.claude_code.compiler.compile import compile_manifest
from adapters.claude_code.compiler.parity import (
    GoldenManifest,
    build_golden_manifest,
    verify_golden_compile,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
TEMPLATES_ROOT = REPO_ROOT / "adapters" / "claude_code" / "templates"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "claude-code-compile" / "golden-manifest.json"
PROJECT_PROFILE = {
    "project_id": "framework-renov",
    "primary_language": "python",
    "package_manager": "pip",
}


def test_golden_manifest_shape() -> None:
    golden = GoldenManifest.load(GOLDEN_PATH)
    assert golden.bundle_version == "1.0.0"
    assert golden.adapter_version == "0.1.0"
    assert len(golden.artifacts) == 51
    kinds = {entry.get("kind") for entry in golden.documented_differences}
    assert "line_endings" in kinds


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


def test_compile_hashes_run_hook_cmd_as_lf_even_if_source_is_crlf(tmp_path: Path) -> None:
    """Root ``*.cmd eol=crlf`` must not leak into frozen hashes (Windows and CI)."""
    from adapters.claude_code.compiler.staging import sha256_bytes

    staging = tmp_path / "staging"
    manifest = compile_manifest(
        BUNDLE_V1,
        staging,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    entry = next(item for item in manifest["artifacts"] if item["path"] == ".claude/hooks/run_hook.cmd")
    on_disk = (staging / ".claude/hooks/run_hook.cmd").read_bytes()
    assert b"\r" not in on_disk
    assert entry["sha256"] == sha256_bytes(on_disk)


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
