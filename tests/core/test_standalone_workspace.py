"""Legacy standalone layout: discovery still works; product cycles are refused."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.orchestrator.git_workspace import head_sha
from governed_ai.core.persistence.paths import resolve_under_root
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import (
    OUT_OF_TREE_REQUIRED_MESSAGE,
    ensure_out_of_tree_ensemble_ready,
)

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


def test_clean_fixture_discovers_as_instance_without_ensemble() -> None:
    workspace = Workspace.discover(CLEAN / "scripts" / "ai-team")
    assert workspace.root == CLEAN.resolve()
    assert workspace.active_ensemble_id is None
    assert workspace.discovered_member_id is None


def test_clean_fixture_without_members_is_not_cycle_ready() -> None:
    workspace = Workspace.from_root(CLEAN)
    assert workspace.instance_root == workspace.root
    # Setup fallback only — not a supported product mode.
    assert workspace.member_root() == workspace.root
    with pytest.raises(GatewayError) as exc:
        ensure_out_of_tree_ensemble_ready(workspace)
    assert exc.value.code == ErrorCode.UNSUPPORTED_CONTRACT
    assert OUT_OF_TREE_REQUIRED_MESSAGE.splitlines()[0] in str(exc.value)


def test_clean_from_root_matches_discover() -> None:
    assert Workspace.from_root(CLEAN).root == Workspace.discover(CLEAN).root


def test_resolve_under_root_keeps_paths_inside_project(tmp_path: Path) -> None:
    inside = resolve_under_root(tmp_path, "src/app.py")
    assert inside == (tmp_path / "src" / "app.py").resolve()
    with pytest.raises(Exception, match="absolute paths"):
        resolve_under_root(tmp_path, str(tmp_path / "other.py"))
    with pytest.raises(Exception, match="path traversal"):
        resolve_under_root(tmp_path, "../outside.py")


def test_head_sha_is_single_git_revision(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "member@example.test")
    _git(tmp_path, "config", "user.name", "Member")
    (tmp_path / "README").write_text("ok\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "test: base")
    sha = head_sha(tmp_path)
    assert len(sha) == 40
    assert sha == sha.lower()


def test_legacy_string_code_revision_remains_schema_valid() -> None:
    schema = _load_schema("evidence.schema.json")
    payload = {
        "id": "EV-LEGACY-STRING",
        "type": "command",
        "code_revision": "0" * 40,
        "command_or_observation": "pytest -q",
        "result": {"status": "passed"},
        "demonstrates": ["unit"],
        "limitations": [],
    }
    Draft202012Validator(schema).validate(payload)


def test_work_unit_without_member_id_remains_schema_valid() -> None:
    schema = _load_schema("work-unit.schema.json")
    payload = {
        "id": "WU-NO-MEMBER",
        "title": "Schema compat",
        "objective": {"result": "optional member_id"},
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
