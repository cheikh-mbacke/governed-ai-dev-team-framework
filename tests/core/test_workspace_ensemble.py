"""Phase 1 Workspace resolution for out-of-tree instance + members (no commands)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from governed_ai.core.workspace import Workspace, WorkspaceError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "distribution" / "payload" / ".ai-team" / "schemas"
SHA_A = "a" * 40
SHA_B = "b" * 40


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _write_instance(root: Path, ensemble_id: str = "boutique") -> Path:
    ai_team = root / ".ai-team"
    ai_team.mkdir()
    (ai_team / "project-profile.yaml").write_text("project:\n  id: acme-ai-team\n", encoding="utf-8")
    members_dir = ai_team / "ensembles" / ensemble_id
    members_dir.mkdir(parents=True)
    return ai_team


def test_discover_follows_member_link_to_instance(tmp_path: Path) -> None:
    instance = tmp_path / "acme-ai-team"
    frontend = tmp_path / "boutique-web"
    instance.mkdir()
    frontend.mkdir()
    _write_instance(instance)
    link = {
        "schema_version": 1,
        "instance_id": "acme-ai-team",
        "ensemble_id": "boutique",
        "member_id": "frontend",
        "instance_path": "../acme-ai-team",
    }
    (frontend / ".ai-team").mkdir()
    (frontend / ".ai-team" / "member-link.json").write_text(
        json.dumps(link), encoding="utf-8"
    )
    workspace = Workspace.discover(frontend / "src")
    assert workspace.root == instance.resolve()
    assert workspace.active_ensemble_id == "boutique"
    assert workspace.discovered_member_id == "frontend"


def test_member_root_resolves_declared_paths(tmp_path: Path) -> None:
    instance = tmp_path / "acme-ai-team"
    backend = tmp_path / "boutique-api"
    frontend = tmp_path / "boutique-web"
    instance.mkdir()
    backend.mkdir()
    frontend.mkdir()
    ai_team = _write_instance(instance)
    members = {
        "ensemble_id": "boutique",
        "members": [
            {"id": "backend", "kind": "service", "path": "../boutique-api"},
            {"id": "frontend", "kind": "ui", "path": "../boutique-web"},
        ],
    }
    (ai_team / "ensembles" / "boutique" / "members.yaml").write_text(
        yaml.safe_dump(members), encoding="utf-8"
    )
    workspace = Workspace(
        root=instance.resolve(),
        active_ensemble_id="boutique",
        discovered_member_id="frontend",
    )
    assert workspace.member_root() == frontend.resolve()
    assert workspace.member_root("backend") == backend.resolve()
    with pytest.raises(WorkspaceError, match="not declared"):
        workspace.member_root("backoffice")


def test_member_root_rejects_instance_path_as_member(tmp_path: Path) -> None:
    instance = tmp_path / "acme-ai-team"
    instance.mkdir()
    ai_team = _write_instance(instance)
    members = {
        "ensemble_id": "boutique",
        "members": [{"id": "backend", "kind": "service", "path": "."}],
    }
    (ai_team / "ensembles" / "boutique" / "members.yaml").write_text(
        yaml.safe_dump(members), encoding="utf-8"
    )
    workspace = Workspace(root=instance.resolve(), active_ensemble_id="boutique")
    with pytest.raises(WorkspaceError, match="must not be the instance root"):
        workspace.member_root("backend")


def test_empty_catalog_schema() -> None:
    schema = _load_schema("catalog.schema.json")
    Draft202012Validator(schema).validate(
        {"schema_version": 1, "instance_id": "acme-ai-team", "ensembles": []}
    )


def test_composition_and_member_link_schemas() -> None:
    Draft202012Validator(_load_schema("composition-revision.schema.json")).validate(
        {
            "id": "CR-20260917-01",
            "ensemble_id": "boutique",
            "kind": "composition",
            "members": {"backend": SHA_A, "frontend": SHA_B},
            "created_at": "2026-09-17T00:00:00Z",
        }
    )
    Draft202012Validator(_load_schema("member-link.schema.json")).validate(
        {
            "schema_version": 1,
            "instance_id": "acme-ai-team",
            "ensemble_id": "boutique",
            "member_id": "frontend",
            "instance_path": "../acme-ai-team",
        }
    )
    Draft202012Validator(_load_schema("ensemble-members.schema.json")).validate(
        {
            "ensemble_id": "boutique",
            "members": [
                {"id": "backend", "kind": "service", "path": "../boutique-api"},
                {"id": "frontend", "kind": "ui", "path": "../boutique-web"},
            ],
        }
    )


def test_evidence_accepts_composition_code_revision() -> None:
    schema = _load_schema("evidence.schema.json")
    Draft202012Validator(schema).validate(
        {
            "id": "EV-COMP",
            "type": "e2e",
            "code_revision": {
                "kind": "composition",
                "composition_id": "CR-20260917-01",
                "members": {"backend": SHA_A, "frontend": SHA_B},
            },
            "command_or_observation": "npm run e2e",
            "result": {"status": "passed"},
            "demonstrates": ["journey"],
            "limitations": [],
        }
    )


def test_work_unit_accepts_optional_member_id() -> None:
    schema = _load_schema("work-unit.schema.json")
    payload = {
        "id": "WU-FRONT",
        "title": "Front",
        "objective": {"result": "page"},
        "scope": {"include": ["src/**"], "exclude": []},
        "expected_behavior": "renders",
        "acceptance_criteria": ["ok"],
        "dependencies": [],
        "risk": {"class": "low"},
        "required_verification": {},
        "status": "ready",
        "revision": 1,
        "created_at": "2026-09-17T00:00:00Z",
        "updated_at": "2026-09-17T00:00:00Z",
        "member_id": "frontend",
    }
    Draft202012Validator(schema).validate(payload)


def test_work_unit_accepts_integration_kind() -> None:
    schema = _load_schema("work-unit.schema.json")
    Draft202012Validator(schema).validate(
        {
            "id": "WU-boutique-integration",
            "title": "boutique integration",
            "kind": "integration",
            "objective": {"result": "integrate members without product writes"},
            "scope": {"include": [], "exclude": ["**"]},
            "expected_behavior": "no product file is written",
            "acceptance_criteria": ["no product write"],
            "dependencies": ["WU-boutique-backend", "WU-boutique-frontend"],
            "risk": {"class": "medium", "reasons": ["cross-member"]},
            "required_verification": {"unit_tests": True},
            "status": "draft",
            "revision": 1,
            "created_at": "2026-09-18T00:00:00Z",
            "updated_at": "2026-09-18T00:00:00Z",
        }
    )
