"""Standalone 0.7.x workspace behaviour — must stay green through 0.8.0."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from governed_ai.core.orchestrator.git_workspace import head_sha
from governed_ai.core.persistence.paths import resolve_under_root
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN = REPO_ROOT / "tests" / "fixtures" / "projects" / "clean"
SCHEMAS = REPO_ROOT / "distribution" / "payload" / ".ai-team" / "schemas"


def _git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root}", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_standalone_discover_from_nested_path_uses_ai_team_root() -> None:
    workspace = Workspace.discover(CLEAN / "scripts" / "ai-team")
    assert workspace.root == CLEAN.resolve()
    assert workspace.active_ensemble_id is None
    assert workspace.discovered_member_id is None


def test_standalone_instance_root_equals_member_root() -> None:
    workspace = Workspace.from_root(CLEAN)
    assert workspace.instance_root == workspace.root
    assert workspace.member_root() == workspace.root
    assert workspace.member_root("frontend") == workspace.root


def test_standalone_from_root_matches_discover() -> None:
    assert Workspace.from_root(CLEAN).root == Workspace.discover(CLEAN).root


def test_standalone_resolve_under_root_keeps_paths_inside_project(tmp_path: Path) -> None:
    inside = resolve_under_root(tmp_path, "src/app.py")
    assert inside == (tmp_path / "src" / "app.py").resolve()
    with pytest.raises(Exception, match="absolute paths"):
        resolve_under_root(tmp_path, str(tmp_path / "other.py"))
    with pytest.raises(Exception, match="path traversal"):
        resolve_under_root(tmp_path, "../outside.py")


def test_standalone_head_sha_is_single_git_revision(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "standalone@example.test")
    _git(tmp_path, "config", "user.name", "Standalone")
    (tmp_path / "README").write_text("ok\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "test: base")
    sha = head_sha(tmp_path)
    assert len(sha) == 40
    assert sha == sha.lower()


def test_standalone_evidence_code_revision_string_remains_valid() -> None:
    schema = _load_schema("evidence.schema.json")
    payload = {
        "id": "EV-STANDALONE",
        "type": "command",
        "code_revision": "0" * 40,
        "command_or_observation": "pytest -q",
        "result": {"status": "passed"},
        "demonstrates": ["unit"],
        "limitations": [],
    }
    Draft202012Validator(schema).validate(payload)


def test_standalone_work_unit_without_member_id_remains_valid() -> None:
    schema = _load_schema("work-unit.schema.json")
    payload = {
        "id": "WU-STANDALONE",
        "title": "Standalone",
        "objective": {"result": "keep 0.7 behaviour"},
        "scope": {"include": ["src/**"], "exclude": []},
        "expected_behavior": "unchanged",
        "acceptance_criteria": ["no member_id required"],
        "dependencies": [],
        "risk": {"class": "low"},
        "required_verification": {"unit_tests": True},
        "status": "ready",
        "revision": 1,
        "created_at": "2026-09-17T00:00:00Z",
        "updated_at": "2026-09-17T00:00:00Z",
    }
    Draft202012Validator(schema).validate(payload)
