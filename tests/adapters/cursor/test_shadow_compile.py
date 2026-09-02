"""WU-P4-SHADOW-COMPILE — shadow compile parity tests."""

from __future__ import annotations

from pathlib import Path

from adapters.cursor.compiler.compile import compile_manifest
from adapters.cursor.compiler.parity import shadow_compare

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
TEMPLATES_ROOT = REPO_ROOT / "adapters" / "cursor" / "templates"
PROJECT_PROFILE = {
    "project_id": "framework-renov",
    "primary_language": "python",
    "package_manager": "pip",
}


def test_compile_output_is_deterministic(tmp_path: Path) -> None:
    """Two compiles from the same templates must produce identical client payload."""
    staging_a = tmp_path / "staging-a"
    staging_b = tmp_path / "staging-b"
    compile_manifest(
        BUNDLE_V1,
        staging_a,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    compile_manifest(
        BUNDLE_V1,
        staging_b,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    report = shadow_compare(
        BUNDLE_V1,
        staging_a / ".cursor",
        staging_b,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    assert report.ok, report.format()
    assert report.diffs == []


def test_shadow_compile_detects_blocking_extra_file(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    report = shadow_compare(
        BUNDLE_V1,
        tmp_path / "empty-historical",
        staging,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    assert not report.ok
    assert any(diff.kind == "extra_in_compile" for diff in report.diffs)


def test_shadow_report_formats_differences(tmp_path: Path) -> None:
    report = shadow_compare(
        BUNDLE_V1,
        tmp_path / "missing-historical",
        tmp_path / "staging",
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    text = report.format()
    assert "Shadow compile divergences" in text
    assert not report.ok
