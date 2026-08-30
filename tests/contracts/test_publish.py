"""WU-P2-PUBLISH — publication, immutability, and active-bundle pointer tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from governed_ai.contracts.bundle_hash import compute_bundle_content_hash
from governed_ai.contracts.compatibility import (
    load_active_bundle_pointer,
    resolve_active_bundle_dir,
)
from governed_ai.contracts.publish import BundlePublishError, publish_bundle
from governed_ai.contracts.validate_bundle import validate_bundle
from tests.contracts.bundle_fixtures import (
    MINIMAL_ROLE,
    write_json,
    write_minimal_bundle,
)

SIDECAR_NAME = "adapter-compiler-notes.yaml"


def test_publish_from_source_to_tmpdir_succeeds(tmp_path: Path) -> None:
    source = write_minimal_bundle(tmp_path / "source")
    target = tmp_path / "contracts"
    result = publish_bundle(source, target)

    assert result.bundle_version == "1.0.0"
    assert result.content_hash.startswith("sha256:")
    assert result.published_dir == target / "bundles" / "1.0.0"
    assert result.published_dir.is_dir()
    assert (result.published_dir / "manifest.json").is_file()
    assert not result.idempotent


def test_published_content_hash_matches_source_and_reproducible(tmp_path: Path) -> None:
    source = write_minimal_bundle(tmp_path / "source")
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    source_hash = compute_bundle_content_hash(source, source_manifest)

    target = tmp_path / "contracts"
    result = publish_bundle(source, target)

    assert result.content_hash == source_hash == source_manifest["content_hash"]

    published_manifest = json.loads(
        (result.published_dir / "manifest.json").read_text(encoding="utf-8")
    )
    again = compute_bundle_content_hash(result.published_dir, published_manifest)
    assert again == result.content_hash

    validation = validate_bundle(result.published_dir)
    assert validation.accepted
    assert validation.content_hash == result.content_hash


def test_tampering_published_file_fails_validate_bundle(tmp_path: Path) -> None:
    """CT-004 style: post-publish mutation breaks content_hash check."""
    source = write_minimal_bundle(tmp_path / "source")
    result = publish_bundle(source, tmp_path / "contracts")
    assert validate_bundle(result.published_dir).accepted

    role_path = result.published_dir / "roles" / "backend-developer.json"
    role = json.loads(role_path.read_text(encoding="utf-8"))
    role["mandate"] = role["mandate"] + " (tampered)"
    write_json(role_path, role)

    broken = validate_bundle(result.published_dir)
    assert not broken.accepted
    assert any("content_hash" in i.message for i in broken.issues)


def test_missing_procedure_ref_publish_fails(tmp_path: Path) -> None:
    role = copy.deepcopy(MINIMAL_ROLE)
    role["procedure_refs"] = [
        {"procedure_id": "missing-procedure", "revision": "1.0.0"},
    ]
    source = write_minimal_bundle(tmp_path / "source", role=role)
    with pytest.raises(BundlePublishError) as excinfo:
        publish_bundle(source, tmp_path / "contracts")
    assert any("missing referenced procedure" in i.message for i in excinfo.value.issues)
    assert not (tmp_path / "contracts" / "bundles" / "1.0.0").exists()


def test_second_publish_same_version_different_content_rejected(tmp_path: Path) -> None:
    source_a = write_minimal_bundle(tmp_path / "source-a")
    target = tmp_path / "contracts"
    first = publish_bundle(source_a, target)

    role = copy.deepcopy(MINIMAL_ROLE)
    role["mandate"] = "Different mandate for a conflicting republish."
    source_b = write_minimal_bundle(tmp_path / "source-b", role=role)
    assert (
        json.loads((source_b / "manifest.json").read_text(encoding="utf-8"))["content_hash"]
        != first.content_hash
    )

    with pytest.raises(BundlePublishError) as excinfo:
        publish_bundle(source_b, target)
    assert "immutable" in str(excinfo.value).lower() or "refusing" in str(excinfo.value).lower()


def test_second_publish_same_version_same_hash_idempotent(tmp_path: Path) -> None:
    source = write_minimal_bundle(tmp_path / "source")
    target = tmp_path / "contracts"
    first = publish_bundle(source, target)
    second = publish_bundle(source, target)

    assert second.idempotent
    assert second.content_hash == first.content_hash
    assert second.bundle_version == first.bundle_version
    assert second.published_dir == first.published_dir


def test_active_bundle_json_points_correctly(tmp_path: Path) -> None:
    source = write_minimal_bundle(tmp_path / "source")
    target = tmp_path / "contracts"
    result = publish_bundle(source, target)

    pointer_path = target / "active-bundle.json"
    assert pointer_path.is_file()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer == {
        "bundle_version": "1.0.0",
        "path": "bundles/1.0.0",
        "content_hash": result.content_hash,
    }
    assert result.active_pointer == pointer

    loaded = load_active_bundle_pointer(target)
    assert loaded["bundle_version"] == "1.0.0"
    assert loaded["content_hash"] == result.content_hash
    assert resolve_active_bundle_dir(target) == result.published_dir.resolve()


def test_sidecar_not_copied_into_published_tree(tmp_path: Path) -> None:
    source = write_minimal_bundle(tmp_path / "source")
    (source / SIDECAR_NAME).write_text(
        "schema_version: 1\nnote: adapter sidecar must not publish\n",
        encoding="utf-8",
    )
    assert (source / SIDECAR_NAME).is_file()

    result = publish_bundle(source, tmp_path / "contracts")
    assert not (result.published_dir / SIDECAR_NAME).exists()
    published_names = {p.name for p in result.published_dir.rglob("*") if p.is_file()}
    assert SIDECAR_NAME not in published_names
