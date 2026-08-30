"""Document 14 §4 — CT-001 .. CT-007 Published Contract Bundle conformity."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from governed_ai.contracts.bundle_hash import compute_bundle_content_hash
from governed_ai.contracts.validate_bundle import validate_bundle
from tests.contracts.bundle_fixtures import (
    MINIMAL_PROCEDURE,
    MINIMAL_ROLE,
    write_json,
    write_minimal_bundle,
)


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_ct001_minimal_valid_bundle_accepted_reproducible_hash(tmp_path: Path) -> None:
    """CT-001: Bundle minimal valide — accepté, hash reproductible."""
    bundle = write_minimal_bundle(tmp_path / "bundle")
    result = validate_bundle(bundle)
    assert result.accepted, [f"{i.code}:{i.message}" for i in result.issues]
    assert result.content_hash is not None
    assert result.content_hash.startswith("sha256:")
    assert len(result.content_hash) == len("sha256:") + 64

    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    again = compute_bundle_content_hash(bundle, manifest)
    assert again == result.content_hash == manifest["content_hash"]

    result2 = validate_bundle(bundle)
    assert result2.accepted
    assert result2.content_hash == result.content_hash


def test_ct002_duplicate_role_id_rejected(tmp_path: Path) -> None:
    """CT-002: RoleId dupliqué — rejet INVALID_SCHEMA / invariant."""
    dup = copy.deepcopy(MINIMAL_ROLE)
    dup["role_id"] = "backend-developer"
    bundle = write_minimal_bundle(
        tmp_path / "bundle",
        extra_roles=[("roles/backend-developer-dup.json", dup)],
    )
    result = validate_bundle(bundle)
    assert not result.accepted
    assert _codes(result) & {"INVALID_SCHEMA", "INVARIANT_VIOLATION"}
    assert any("duplicate role_id" in i.message for i in result.issues)


def test_ct003_missing_referenced_procedure_rejected(tmp_path: Path) -> None:
    """CT-003: Procédure référencée absente — rejet avant publication."""
    role = copy.deepcopy(MINIMAL_ROLE)
    role["procedure_refs"] = [
        {"procedure_id": "missing-procedure", "revision": "1.0.0"},
    ]
    bundle = write_minimal_bundle(tmp_path / "bundle", role=role)
    result = validate_bundle(bundle)
    assert not result.accepted
    assert any("missing referenced procedure" in i.message for i in result.issues)
    assert "INVARIANT_VIOLATION" in _codes(result)


def test_ct004_bundle_modified_after_hash_rejected(tmp_path: Path) -> None:
    """CT-004: Bundle modifié après calcul du hash — rejet."""
    bundle = write_minimal_bundle(tmp_path / "bundle")
    assert validate_bundle(bundle).accepted

    role_path = bundle / "roles" / "backend-developer.json"
    role = json.loads(role_path.read_text(encoding="utf-8"))
    role["mandate"] = role["mandate"] + " (tampered)"
    write_json(role_path, role)

    result = validate_bundle(bundle)
    assert not result.accepted
    assert any("content_hash" in i.message for i in result.issues)
    assert "INVARIANT_VIOLATION" in _codes(result)


def test_ct005_adapter_syntax_in_agnostic_field_rejected(tmp_path: Path) -> None:
    """CT-005: Syntaxe adaptateur dans champ agnostique — rejet lint de frontière."""
    # Build forbidden token without storing it in contracts production code.
    leak = "." + "cursor"
    role = copy.deepcopy(MINIMAL_ROLE)
    role["mandate"] = f"Write under {leak}/agents only."
    bundle = write_minimal_bundle(tmp_path / "bundle", role=role)
    result = validate_bundle(bundle)
    assert not result.accepted
    assert any("boundary lint" in i.message for i in result.issues)
    assert "INVARIANT_VIOLATION" in _codes(result)


def test_ct006_unknown_or_removed_required_field_rejected(tmp_path: Path) -> None:
    """CT-006: Champ obligatoire inconnu/supprimé — rejet selon version majeure."""
    bundle = write_minimal_bundle(tmp_path / "ok")
    assert validate_bundle(bundle).accepted

    # Unknown (non-namespaced) field
    role = copy.deepcopy(MINIMAL_ROLE)
    role["unknown_field"] = "nope"
    bad_unknown = write_minimal_bundle(tmp_path / "unknown", role=role)
    r1 = validate_bundle(bad_unknown)
    assert not r1.accepted
    assert "INVALID_SCHEMA" in _codes(r1)

    # Removed required field
    role2 = copy.deepcopy(MINIMAL_ROLE)
    del role2["mandate"]
    bad_missing = write_minimal_bundle(tmp_path / "missing", role=role2)
    r2 = validate_bundle(bad_missing)
    assert not r2.accepted
    assert "INVALID_SCHEMA" in _codes(r2)


def test_ct007_namespaced_extension_preserved(tmp_path: Path) -> None:
    """CT-007: Extension namespacée autorisée — préservée sans changer la sémantique Core."""
    role = copy.deepcopy(MINIMAL_ROLE)
    role["x-vendor-meta"] = {"hint": "preserve-me", "priority": 1}
    proc = copy.deepcopy(MINIMAL_PROCEDURE)
    proc["x-vendor-meta"] = {"stage": "alpha"}

    bundle = write_minimal_bundle(tmp_path / "bundle", role=role, procedure=proc)
    result = validate_bundle(bundle)
    assert result.accepted, [f"{i.code}:{i.message}" for i in result.issues]
    assert result.roles["backend-developer"]["x-vendor-meta"] == {
        "hint": "preserve-me",
        "priority": 1,
    }
    assert result.procedures["implement-work-unit"]["x-vendor-meta"] == {"stage": "alpha"}
    # Core fields unchanged
    assert result.roles["backend-developer"]["role_id"] == "backend-developer"
    assert result.procedures["implement-work-unit"]["procedure_id"] == "implement-work-unit"
