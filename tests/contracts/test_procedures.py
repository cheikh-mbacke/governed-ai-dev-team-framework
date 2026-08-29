"""WU-P2-PROCEDURES — ProcedureRevision bundle transcription tests."""

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
ADAPTER_CURSOR_ROOT = Path(__file__).resolve().parents[2] / "adapters" / "cursor"
PROCEDURES_DIR = BUNDLE_V1 / "procedures"
MANIFEST_PATH = BUNDLE_V1 / "manifest.json"

EXPECTED_PROCEDURE_IDS = (
    "audit-release",
    "build-context",
    "compile-project",
    "frontend-design",
    "impact-analysis",
    "implement-work-unit",
    "orchestrator",
    "prepare-acceptance",
    "propose-profile",
    "retrospective",
    "security-review",
    "verify-work-unit",
    "webapp-testing",
)

STEP_FORBIDDEN_TOKENS = (
    "Cursor IDE",
    "MCP",
    "hooks.json",
    "permissions.json",
    "cli.json",
    ".cursor",
    "Cursor",
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def procedure_documents() -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for procedure_id in EXPECTED_PROCEDURE_IDS:
        path = PROCEDURES_DIR / f"{procedure_id}.json"
        assert path.is_file(), f"missing procedure file: {path.name}"
        docs[procedure_id] = json.loads(path.read_text(encoding="utf-8"))
    return docs


def test_all_procedure_files_exist_and_validate_schema(
    procedure_documents: dict[str, dict],
) -> None:
    for procedure_id, doc in procedure_documents.items():
        issues = validate_document(doc, "procedure")
        assert issues == [], (
            f"{procedure_id}: {[f'{i.path}: {i.message}' for i in issues]}"
        )
        assert doc["procedure_id"] == procedure_id
        assert doc["revision"] == "1.0.0"
        assert len(doc["steps"]) >= 3, f"{procedure_id}: steps look like a stub"


def test_manifest_lists_all_procedures(manifest: dict) -> None:
    listed = {Path(rel).stem for rel in manifest["procedures"]}
    assert listed == set(EXPECTED_PROCEDURE_IDS)


def test_each_referenced_procedure_resolves(procedure_documents: dict[str, dict]) -> None:
    roles_dir = BUNDLE_V1 / "roles"
    referenced: set[str] = set()
    for role_path in roles_dir.glob("*.json"):
        role = json.loads(role_path.read_text(encoding="utf-8"))
        for ref in role.get("procedure_refs") or []:
            referenced.add(ref["procedure_id"])
    missing = referenced - set(procedure_documents)
    assert missing == set(), f"roles reference missing procedures: {sorted(missing)}"


def test_v1_bundle_validate_bundle_passes() -> None:
    result = validate_bundle(BUNDLE_V1)
    assert result.accepted, [f"{i.code}:{i.message}" for i in result.issues]
    assert result.content_hash is not None
    assert len(result.procedures) == len(EXPECTED_PROCEDURE_IDS)


@pytest.mark.parametrize("procedure_id", EXPECTED_PROCEDURE_IDS)
def test_lint_agnostic_boundary_passes_per_procedure(procedure_id: str) -> None:
    path = PROCEDURES_DIR / f"{procedure_id}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    rel = f"procedures/{procedure_id}.json"
    issues = lint_agnostic_boundary(doc, rel)
    assert issues == [], [f"{i.path}: {i.message}" for i in issues]


@pytest.mark.parametrize("procedure_id", EXPECTED_PROCEDURE_IDS)
def test_no_forbidden_tokens_in_procedure_content(procedure_id: str) -> None:
    text = (PROCEDURES_DIR / f"{procedure_id}.json").read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in text, f"{procedure_id}.json contains forbidden token {token!r}"


@pytest.mark.parametrize("procedure_id", EXPECTED_PROCEDURE_IDS)
def test_steps_are_agnostic(procedure_id: str) -> None:
    doc = json.loads((PROCEDURES_DIR / f"{procedure_id}.json").read_text(encoding="utf-8"))
    for idx, step in enumerate(doc["steps"]):
        for token in STEP_FORBIDDEN_TOKENS:
            assert token not in step, (
                f"{procedure_id}.json steps[{idx}] contains forbidden token {token!r}"
            )


def test_adapter_compiler_notes_sidecar_exists() -> None:
    sidecar = ADAPTER_CURSOR_ROOT / "compiler-notes.yaml"
    assert sidecar.is_file(), "adapter compiler sidecar required under adapters/cursor/"
    text = sidecar.read_text(encoding="utf-8")
    assert "implement-work-unit" in text
    assert "orchestrator" in text
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "compiler-notes.yaml" not in json.dumps(manifest)
