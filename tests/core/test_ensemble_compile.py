"""Phase 5: ensemble reconciliation fingerprints and tagged Work Units."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tests.core.workspace_helpers import (
    FABRIC_ROOT,
    PAYLOAD_AI_TEAM,
    write_installed_client_profile,
)

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.ensemble_compile import plan_ensemble_work_units
from governed_ai.core.persistence.lock import force_release_stale_lock
from governed_ai.core.reconciliation import (
    fingerprint_ensemble,
    fingerprint_project,
    new_report,
    semantic_issues,
)
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
RECONCILE = REPO_ROOT / "scripts" / "ai-team" / "reconcile_project.py"


@pytest.fixture()
def instance_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="acme-ai-team")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: not_compiled\n", encoding="utf-8")
    (ai_team / "work-units").mkdir(parents=True)
    return Workspace.from_root(tmp_path)


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


def _repository(root: Path, filename: str, content: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "member@example.test")
    _git(root, "config", "user.name", "Member")
    (root / filename).write_text(content, encoding="utf-8")
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / filename).write_text(content, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "test: base")
    return root


def _actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-p5",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _execute(workspace: Workspace, envelope: dict) -> tuple[dict, int]:
    force_release_stale_lock(workspace.ai_team / "locks" / "project.lock")
    return CommandGateway(workspace).execute_command(envelope)


def _register_two_members(workspace: Workspace, tmp_path: Path) -> tuple[Path, Path]:
    backend = _repository(tmp_path / "boutique-api", "api.py", "print(1)\n")
    frontend = _repository(tmp_path / "boutique-web", "page.js", "export default {}\n")
    for envelope in (
        {
            "protocol_version": "1.0",
            "command_id": "CMD-ens-p5",
            "idempotency_key": "idem-ens-p5",
            "correlation_id": "COR-p5",
            "type": "RegisterEnsemble",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique"},
            "payload": {"id": "boutique"},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-mem-be",
            "idempotency_key": "idem-mem-be",
            "correlation_id": "COR-p5",
            "type": "RegisterMember",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique", "expected_revision": 1},
            "payload": {"id": "backend", "kind": "service", "path": str(backend)},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-mem-fe",
            "idempotency_key": "idem-mem-fe",
            "correlation_id": "COR-p5",
            "type": "RegisterMember",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique", "expected_revision": 2},
            "payload": {"id": "frontend", "kind": "ui", "path": str(frontend)},
        },
        {
            "protocol_version": "1.0",
            "command_id": "CMD-act-p5",
            "idempotency_key": "idem-act-p5",
            "correlation_id": "COR-p5",
            "type": "SetActiveEnsemble",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "ensemble", "id": "boutique"},
            "payload": {"ensemble_id": "boutique"},
        },
    ):
        receipt, code = _execute(workspace, envelope)
        assert code == 0, receipt
    return backend, frontend


def test_fingerprint_ensemble_changes_when_one_member_changes(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    backend, frontend = _register_two_members(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    before, members_before = fingerprint_ensemble(workspace)
    assert set(members_before) == {"backend", "frontend"}
    (frontend / "src" / "page.js").write_text("export default { changed: true }\n", encoding="utf-8")
    after, members_after = fingerprint_ensemble(workspace)
    assert after.digest != before.digest
    assert members_after["frontend"].digest != members_before["frontend"].digest
    assert members_after["backend"].digest == members_before["backend"].digest
    assert fingerprint_project(backend).digest == members_after["backend"].digest
    issues = semantic_issues(
        {
            "schema_version": 1,
            "project_id": "boutique",
            "status": "ready",
            "scope": {"include": ["."], "exclude": []},
            "human_material": {},
            "inventory": {"generated_at": "2026-09-18T00:00:00Z", "entries": []},
            "convergence": [],
            "decisions": [],
            "verification": {"commands": [{"command": "true", "status": "pass"}], "blocking_conflicts": 0},
            "baseline": {
                **before.as_dict(),
                "members": {
                    member_id: {"digest": item.digest, "file_count": item.file_count}
                    for member_id, item in members_before.items()
                },
            },
        },
        root=workspace.root,
        workspace=workspace,
        require_ready=True,
        verify_fingerprint=True,
    )
    assert any("member 'frontend'" in issue and "stale" in issue for issue in issues)


def test_reconciliation_report_path_follows_active_ensemble(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    standalone = Workspace.from_root(instance_workspace.root)
    assert standalone.reconciliation_report_path == (
        instance_workspace.root / ".ai-team" / "reconciliation" / "baseline.yaml"
    )
    _register_two_members(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    assert workspace.reconciliation_report_path == (
        workspace.ensembles_root / "boutique" / "reconciliation" / "baseline.yaml"
    )


def test_new_report_inventories_each_member(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_two_members(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    report = new_report("boutique", workspace.root, "2026-09-18T00:00:00Z", workspace=workspace)
    paths = {entry["path"] for entry in report["inventory"]["entries"]}
    assert any(path.startswith("backend:") for path in paths)
    assert any(path.startswith("frontend:") for path in paths)


def test_plan_ensemble_work_units_tags_members_and_integration(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_two_members(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    payloads = plan_ensemble_work_units(workspace)
    member_ids = {item.get("member_id") for item in payloads if item.get("kind") != "integration"}
    assert member_ids == {"backend", "frontend"}
    integration = next(item for item in payloads if item.get("kind") == "integration")
    assert integration.get("member_id") is None
    assert integration["scope"]["include"] == []
    assert set(integration["dependencies"]) == {
        "WU-boutique-backend",
        "WU-boutique-frontend",
    }


def test_create_work_unit_requires_member_id_on_multi_member_ensemble(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    _register_two_members(instance_workspace, tmp_path)
    workspace = Workspace.from_root(instance_workspace.root)
    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-wu-bare",
            "idempotency_key": "idem-wu-bare",
            "correlation_id": "COR-p5",
            "type": "CreateWorkUnit",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "work_unit", "id": "WU-BARE"},
            "payload": {
                "id": "WU-BARE",
                "title": "untagged",
                "objective": {"result": "no"},
                "scope": {"include": ["."], "exclude": []},
                "expected_behavior": "must be rejected",
                "acceptance_criteria": ["no"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
            },
        },
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value

    for payload in plan_ensemble_work_units(workspace):
        work_unit_id = payload["id"]
        receipt, code = _execute(
            workspace,
            {
                "protocol_version": "1.0",
                "command_id": f"CMD-{work_unit_id}",
                "idempotency_key": f"idem-{work_unit_id}",
                "correlation_id": "COR-p5",
                "type": "CreateWorkUnit",
                "issued_at": "2026-09-18T12:00:00Z",
                "actor": _actor(),
                "target": {"kind": "work_unit", "id": work_unit_id},
                "payload": payload,
            },
        )
        assert code == 0, receipt
    integration = yaml.safe_load(
        (workspace.ai_team / "work-units" / "WU-boutique-integration.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert integration["kind"] == "integration"
    assert not integration["scope"]["include"]

    receipt, code = _execute(
        workspace,
        {
            "protocol_version": "1.0",
            "command_id": "CMD-wu-int-bad",
            "idempotency_key": "idem-wu-int-bad",
            "correlation_id": "COR-p5",
            "type": "CreateWorkUnit",
            "issued_at": "2026-09-18T12:00:00Z",
            "actor": _actor(),
            "target": {"kind": "work_unit", "id": "WU-INT-BAD"},
            "payload": {
                "id": "WU-INT-BAD",
                "title": "bad integration",
                "kind": "integration",
                "member_id": "backend",
                "objective": {"result": "no"},
                "scope": {"include": ["src/**"], "exclude": []},
                "expected_behavior": "must be rejected",
                "acceptance_criteria": ["no"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
            },
        },
    )
    assert code != 0
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_reconcile_from_member_checkout_is_rejected(
    instance_workspace: Workspace, tmp_path: Path
) -> None:
    backend, _frontend = _register_two_members(instance_workspace, tmp_path)
    completed = subprocess.run(
        [sys.executable, str(RECONCILE), "check"],
        cwd=backend,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode != 0
    combined = completed.stdout + completed.stderr
    assert str(instance_workspace.root) in combined
    assert "member" in combined.lower()


def test_compile_skill_stops_on_member_link() -> None:
    for relative in (
        Path("adapters") / "cursor" / "templates" / ".cursor" / "skills" / "compile-project" / "SKILL.md",
        Path("adapters") / "claude_code" / "templates" / ".claude" / "skills" / "compile-project" / "SKILL.md",
        Path("adapters") / "cursor" / "templates" / ".cursor" / "skills" / "reconcile-project" / "SKILL.md",
        Path("adapters") / "claude_code" / "templates" / ".claude" / "skills" / "reconcile-project" / "SKILL.md",
    ):
        skill = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "member-link.json" in skill
        assert "instance_path" in skill
