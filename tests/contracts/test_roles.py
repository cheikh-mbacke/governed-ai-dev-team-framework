"""WU-P2-ROLES — RoleDefinitionRevision bundle transcription tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.architecture.test_named_tool_leaks import FORBIDDEN_TOKENS

from governed_ai.contracts.validate_bundle import (
    lint_agnostic_boundary,
    validate_bundle,
    validate_document,
)

BUNDLE_V1 = (
    Path(__file__).resolve().parents[2] / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
)
ROLES_DIR = BUNDLE_V1 / "roles"

EXPECTED_ROLE_IDS = (
    "backend-developer",
    "frontend-developer",
    "qa-test",
    "code-reviewer",
    "security-reviewer",
    "auditor",
    "release-agent",
    "architect",
    "product-analyst",
    "control-plane",
)

WRITES_AXES = (
    "product",
    "authoritative_governance_commands",
    "non_authoritative_signal_commands",
)


@pytest.fixture(scope="module")
def role_documents() -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for role_id in EXPECTED_ROLE_IDS:
        path = ROLES_DIR / f"{role_id}.json"
        assert path.is_file(), f"missing role file: {path.name}"
        docs[role_id] = json.loads(path.read_text(encoding="utf-8"))
    return docs


def test_all_role_files_exist_and_validate_schema(role_documents: dict[str, dict]) -> None:
    for role_id, doc in role_documents.items():
        issues = validate_document(doc, "role")
        assert issues == [], f"{role_id}: {[f'{i.path}: {i.message}' for i in issues]}"
        assert doc["role_id"] == role_id


def test_each_role_has_three_writes_axes(role_documents: dict[str, dict]) -> None:
    for role_id, doc in role_documents.items():
        writes = doc.get("writes")
        assert isinstance(writes, dict), f"{role_id}: writes must be an object"
        for axis in WRITES_AXES:
            assert axis in writes, f"{role_id}: missing writes.{axis}"


def test_v1_bundle_validate_bundle_passes() -> None:
    result = validate_bundle(BUNDLE_V1)
    assert result.accepted, [f"{i.code}:{i.message}" for i in result.issues]
    assert result.content_hash is not None
    assert len(result.roles) == len(EXPECTED_ROLE_IDS)


@pytest.mark.parametrize("role_id", EXPECTED_ROLE_IDS)
def test_lint_agnostic_boundary_passes_per_role(role_id: str) -> None:
    path = ROLES_DIR / f"{role_id}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    rel = f"roles/{role_id}.json"
    issues = lint_agnostic_boundary(doc, rel)
    assert issues == [], [f"{i.path}: {i.message}" for i in issues]


@pytest.mark.parametrize("role_id", EXPECTED_ROLE_IDS)
def test_no_forbidden_tokens_in_role_content(role_id: str) -> None:
    text = (ROLES_DIR / f"{role_id}.json").read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in text, f"{role_id}.json contains forbidden token {token!r}"


def test_control_plane_has_orchestrator_governance_commands(
    role_documents: dict[str, dict],
) -> None:
    cp = role_documents["control-plane"]
    auth = cp["writes"]["authoritative_governance_commands"]
    assert "CreateWorkUnit" in auth
    assert "TransitionWorkUnit" in auth
    assert "RegisterEvidence" in auth
    assert cp["writes"]["non_authoritative_signal_commands"] == ["RecordObservation"]


def test_product_write_levels_match_catalogue(role_documents: dict[str, dict]) -> None:
    expected = {
        "backend-developer": "scoped",
        "frontend-developer": "scoped",
        "qa-test": "tests_only",
        "code-reviewer": "none",
        "security-reviewer": "none",
        "auditor": "none",
        "release-agent": "none",
        "architect": "none",
        "product-analyst": "none",
        "control-plane": "none",
    }
    for role_id, level in expected.items():
        assert role_documents[role_id]["writes"]["product"]["level"] == level
