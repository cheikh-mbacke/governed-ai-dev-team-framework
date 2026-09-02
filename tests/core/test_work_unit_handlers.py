"""WU-P3-GW-WU — CreateWorkUnit, TransitionWorkUnit and state machine tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.work_unit.state_machine import (
    iter_forbidden_transitions,
    iter_permitted_transitions,
)
from governed_ai.core.workspace import Workspace

from tests.core.workspace_helpers import FABRIC_ROOT, PAYLOAD_AI_TEAM, write_installed_client_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


def _minimal_work_unit_payload(work_unit_id: str, **overrides) -> dict:
    base = {
        "id": work_unit_id,
        "title": "Test work unit",
        "objective": {"result": "test"},
        "scope": {"include": [], "exclude": []},
        "expected_behavior": "test behavior",
        "acceptance_criteria": ["ok"],
        "dependencies": [],
        "risk": {"class": "low", "reasons": []},
        "required_verification": {"unit_tests": True},
    }
    base.update(overrides)
    return base


@pytest.fixture()
def wu_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team)
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    (ai_team / "work-units").mkdir(parents=True)
    (ai_team / "state").mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: execution\n", encoding="utf-8")
    return Workspace.from_root(tmp_path)


def _actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-wu-test",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _create_envelope(work_unit_id: str, **payload_overrides) -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-create-{work_unit_id}",
        "idempotency_key": f"idem-create-{work_unit_id}",
        "correlation_id": "COR-wu-create",
        "type": "CreateWorkUnit",
        "issued_at": "2026-08-29T17:30:00Z",
        "actor": _actor(),
        "target": {"kind": "work_unit", "id": work_unit_id},
        "payload": _minimal_work_unit_payload(work_unit_id, **payload_overrides),
    }


def _transition_envelope(
    work_unit_id: str,
    *,
    expected_revision: int,
    to_status: str,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-trans-{work_unit_id}-{to_status}",
        "idempotency_key": idempotency_key or f"idem-trans-{work_unit_id}-{to_status}",
        "correlation_id": "COR-wu-trans",
        "type": "TransitionWorkUnit",
        "issued_at": "2026-08-29T17:31:00Z",
        "actor": _actor(),
        "target": {
            "kind": "work_unit",
            "id": work_unit_id,
            "expected_revision": expected_revision,
        },
        "payload": {"to_status": to_status, "reason": "state machine test"},
    }


def _seed_work_unit(
    workspace: Workspace,
    work_unit_id: str,
    *,
    status: str = "ready",
    revision: int = 1,
    **document_overrides,
) -> None:
    document = _minimal_work_unit_payload(work_unit_id, status=status, **document_overrides)
    document["revision"] = revision
    document.setdefault("events", [])
    document.setdefault("evidence", [])
    document.setdefault(
        "outcomes",
        {
            "review_status": "pending",
            "audit_status": "not_required",
            "critical_open_items": [],
            "defects": [],
            "audit_findings": [],
            "human_acceptance": None,
        },
    )
    path = workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def test_create_work_unit_via_gateway(wu_workspace: Workspace) -> None:
    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(_create_envelope("WU-CREATE-001"))
    assert exit_code == 0
    assert receipt["status"] == "accepted"
    created = yaml.safe_load(
        (wu_workspace.ai_team / "work-units" / "WU-CREATE-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert created["status"] == "draft"
    assert created["revision"] == 1


def test_create_work_unit_rejects_duplicate(wu_workspace: Workspace) -> None:
    gateway = CommandGateway(wu_workspace)
    gateway.execute_command(_create_envelope("WU-DUP-001"))
    duplicate = _create_envelope("WU-DUP-001")
    duplicate["idempotency_key"] = "idem-create-WU-DUP-001-retry"
    duplicate["command_id"] = "CMD-create-WU-DUP-001-retry"
    receipt, exit_code = gateway.execute_command(duplicate)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.ALREADY_EXISTS.value


def test_cg003_stale_revision_on_transition(wu_workspace: Workspace) -> None:
    _seed_work_unit(wu_workspace, "WU-STALE-001", status="ready")
    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope("WU-STALE-001", expected_revision=99, to_status="in_progress")
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


@pytest.mark.parametrize("from_status,to_status", iter_permitted_transitions())
def test_permitted_transitions_accepted(
    wu_workspace: Workspace, from_status: str, to_status: str
) -> None:
    work_unit_id = f"WU-PERM-{from_status}-{to_status}".replace("_", "-")
    _seed_work_unit(wu_workspace, work_unit_id, status=from_status)
    if to_status == "done":
        path = wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["evidence"] = ["EV-test"]
        document["outcomes"]["review_status"] = "approved"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status=to_status)
    )
    assert exit_code == 0, receipt
    updated = yaml.safe_load(
        (wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert updated["status"] == to_status
    assert updated["revision"] == 2


@pytest.mark.parametrize("from_status,to_status", iter_forbidden_transitions())
def test_forbidden_transitions_rejected(
    wu_workspace: Workspace, from_status: str, to_status: str
) -> None:
    work_unit_id = f"WU-FORB-{from_status}-{to_status}".replace("_", "-")
    _seed_work_unit(wu_workspace, work_unit_id, status=from_status)
    before = (
        wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml"
    ).read_text(encoding="utf-8")

    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope(work_unit_id, expected_revision=1, to_status=to_status)
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_TRANSITION.value
    after = (wu_workspace.ai_team / "work-units" / f"{work_unit_id}.yaml").read_text(
        encoding="utf-8"
    )
    assert before == after


def test_done_transition_requires_prerequisites(wu_workspace: Workspace) -> None:
    _seed_work_unit(wu_workspace, "WU-DONE-GUARD", status="verification")
    gateway = CommandGateway(wu_workspace)
    receipt, exit_code = gateway.execute_command(
        _transition_envelope("WU-DONE-GUARD", expected_revision=1, to_status="done")
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


def test_work_unit_done_query(wu_workspace: Workspace) -> None:
    _seed_work_unit(wu_workspace, "WU-QUERY-DONE", status="verification")
    gateway = CommandGateway(wu_workspace)
    result = gateway.query("work-unit-done", args={"work_unit_id": "WU-QUERY-DONE"})
    assert result["done"] is False
    assert "evidence" in result["missing"]
