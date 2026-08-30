"""WU-P4-MANIFEST-COMPILER — Cursor bundle compiler tests (CT-010, AD-002)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from adapters.cursor.compiler.compile import ADAPTER_ID, ADAPTER_VERSION, compile_manifest
from adapters.cursor.compiler.staging import resolve_under_staging, validate_pre_install

from governed_ai.adapters.cursor import CursorAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
TEMPLATES_ROOT = REPO_ROOT / "adapters" / "cursor" / "templates"
ADAPTER_MANIFEST = REPO_ROOT / "adapters" / "cursor" / "manifest.json"
PROJECT_PROFILE = {
    "project_id": "framework-renov",
    "primary_language": "python",
    "package_manager": "pip",
}


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    return tmp_path / "staging"


def test_adapter_manifest_descriptor_matches_spi() -> None:
    data = json.loads(ADAPTER_MANIFEST.read_text(encoding="utf-8"))
    assert data["adapter_id"] == ADAPTER_ID
    assert data["adapter_version"] == ADAPTER_VERSION
    assert "1.0" in data["protocol_versions"]
    assert data["capabilities"]["per_role_readonly"] is True


def test_ad002_compilation_produces_complete_staged_manifest(staging_dir: Path) -> None:
    manifest = compile_manifest(
        BUNDLE_V1,
        staging_dir,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )

    assert manifest["adapter_id"] == "cursor"
    assert manifest["bundle_version"] == "1.0.0"
    assert manifest["artifacts"]

    paths = {entry["path"] for entry in manifest["artifacts"]}
    assert ".cursor/hooks.json" in paths
    assert ".cursor/permissions.json" in paths
    assert ".cursor/cli.json" in paths
    assert any(p.startswith(".cursor/agents/") for p in paths)
    assert any("/skills/" in p for p in paths)

    for entry in manifest["artifacts"]:
        rel = entry["path"]
        assert not Path(rel).is_absolute()
        target = resolve_under_staging(staging_dir, rel)
        assert target.is_file()
        assert entry["sha256"].startswith("sha256:")

    validate_pre_install(staging_dir, manifest)


def test_ct010_double_compilation_is_byte_identical(staging_dir: Path) -> None:
    staging_a = staging_dir / "a"
    staging_b = staging_dir / "b"

    manifest_a = compile_manifest(
        BUNDLE_V1,
        staging_a,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )
    manifest_b = compile_manifest(
        BUNDLE_V1,
        staging_b,
        PROJECT_PROFILE,
        templates_root=TEMPLATES_ROOT,
    )

    assert manifest_a == manifest_b
    for entry in manifest_a["artifacts"]:
        rel = entry["path"]
        assert (staging_a / rel).read_bytes() == (staging_b / rel).read_bytes()


def test_compile_rejects_invalid_bundle(tmp_path: Path, staging_dir: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text('{"schema_version": 1}', encoding="utf-8")

    with pytest.raises(ValueError, match="bundle validation failed"):
        compile_manifest(broken, staging_dir, PROJECT_PROFILE, templates_root=TEMPLATES_ROOT)


def test_ad012_rejects_manifest_path_outside_staging(staging_dir: Path) -> None:
    manifest = {
        "adapter_id": "cursor",
        "adapter_version": ADAPTER_VERSION,
        "bundle_version": "1.0.0",
        "artifacts": [
            {
                "kind": "agent",
                "path": "../outside.txt",
                "sha256": "sha256:00",
            }
        ],
    }
    with pytest.raises(ValueError, match="escapes staging"):
        validate_pre_install(staging_dir, manifest)


def test_cursor_adapter_spi_compile(staging_dir: Path, tmp_path: Path) -> None:
    bundle_manifest = json.loads((BUNDLE_V1 / "manifest.json").read_text(encoding="utf-8"))
    adapter = CursorAdapter(
        project_root=tmp_path,
        bundle_dir=BUNDLE_V1,
        staging_dir=staging_dir,
        templates_root=TEMPLATES_ROOT,
    )
    descriptor = adapter.describe()
    assert descriptor["adapter_id"] == "cursor"

    artifact_manifest = adapter.compile(bundle_manifest, PROJECT_PROFILE)
    assert artifact_manifest["bundle_version"] == "1.0.0"
    validate_pre_install(staging_dir, dict(artifact_manifest))
