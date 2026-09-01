"""WU-P3-GW-DEC-FIND — Decision Request and Finding gateway handlers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.decisions.state_machine import (
    iter_forbidden_transitions,
    iter_permitted_transitions,
)
from governed_ai.core.workspace import Workspace

from tests.core.workspace_helpers import write_installed_client_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def dec_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = REPO_ROOT / ".ai-team"
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team)
    shutil.copy2(source / "framework-version.json", ai_team / "framework-version.json")
    for directory in ("decisions", "findings", "work-units", "state", "authorizations"):
        (ai_team / directory).mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text("phase: execution\n", encoding="utf-8")
    (ai_team / "work-units" / "WU-FIND-REF.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-FIND-REF",
                "title": "Finding reference target",
                "objective": {"result": "test"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "test",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
                "status": "verification",
                "revision": 1,
                "outcomes": {"audit_findings": []},
            }
        ),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _human_auth(auth_id: str = "HAUTH-test-001") -> dict:
    return {
        "authorization_id": auth_id,
        "granted_by": "test-human",
        "granted_at": "2026-08-29T17:45:00Z",
        "scope": "decision:DEC-TEST-001",
        "consumed_at": None,
    }


def _control_plane_actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-dec-test",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _auditor_actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-audit-test",
        "role_id": "auditor",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _decision_payload(decision_id: str, **overrides) -> dict:
    base = {
        "id": decision_id,
        "question": "Which option?",
        "why_human_authority_is_required": "Human product authority required.",
        "options": [{"id": "a", "label": "Option A"}, {"id": "b", "label": "Option B"}],
        "status": "pending_human",
    }
    base.update(overrides)
    return base


def _create_decision_envelope(decision_id: str, **payload_overrides) -> dict:
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-create-{decision_id}",
        "idempotency_key": f"idem-create-{decision_id}",
        "correlation_id": "COR-dec-create",
        "type": "CreateDecisionRequest",
        "issued_at": "2026-08-29T17:45:00Z",
        "actor": _control_plane_actor(),
        "target": {"kind": "decision_request", "id": decision_id},
        "payload": _decision_payload(decision_id, **payload_overrides),
    }


def _resolve_decision_envelope(
    decision_id: str,
    *,
    expected_revision: int,
    to_status: str,
    auth_id: str = "HAUTH-test-001",
    **payload_overrides,
) -> dict:
    payload = {"to_status": to_status, **payload_overrides}
    if to_status == "decided":
        payload.setdefault(
            "decision",
            {
                "selected_option": "a",
                "decided_by": "test-human",
                "decided_at": "2026-08-29T17:46:00Z",
                "rationale": "Option A selected.",
            },
        )
    return {
        "protocol_version": "1.0",
        "command_id": f"CMD-resolve-{decision_id}-{to_status}",
        "idempotency_key": f"idem-resolve-{decision_id}-{to_status}-{auth_id}",
        "correlation_id": "COR-dec-resolve",
        "type": "ResolveDecisionRequest",
        "issued_at": "2026-08-29T17:46:00Z",
        "actor": _control_plane_actor(),
        "target": {
            "kind": "decision_request",
            "id": decision_id,
            "expected_revision": expected_revision,
        },
        "payload": payload,
        "human_authorization": _human_auth(auth_id),
    }


def _seed_decision(workspace: Workspace, decision_id: str, *, status: str, revision: int = 1) -> None:
    document = _decision_payload(decision_id, status=status)
    document["revision"] = revision
    if status == "decided":
        document["decision"] = {
            "selected_option": "a",
            "decided_by": "seed",
            "decided_at": "2026-08-29T17:00:00Z",
            "rationale": "seed",
        }
    path = workspace.ai_team / "decisions" / f"{decision_id}.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def test_create_decision_request_via_gateway(dec_workspace: Workspace) -> None:
    gateway = CommandGateway(dec_workspace)
    receipt, exit_code = gateway.execute_command(_create_decision_envelope("DEC-CREATE-001"))
    assert exit_code == 0
    created = yaml.safe_load(
        (dec_workspace.ai_team / "decisions" / "DEC-CREATE-001.yaml").read_text(encoding="utf-8")
    )
    assert created["status"] == "pending_human"
    assert created["revision"] == 1
    assert "decision" not in created


def test_resolve_decision_requires_human_authorization(dec_workspace: Workspace) -> None:
    _seed_decision(dec_workspace, "DEC-NO-AUTH", status="pending_human")
    envelope = _resolve_decision_envelope("DEC-NO-AUTH", expected_revision=1, to_status="decided")
    del envelope["human_authorization"]
    gateway = CommandGateway(dec_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.HUMAN_AUTH_REQUIRED.value


@pytest.mark.parametrize("from_status,to_status", iter_permitted_transitions())
def test_permitted_decision_transitions(
    dec_workspace: Workspace, from_status: str, to_status: str
) -> None:
    decision_id = f"DEC-PERM-{from_status}-{to_status}".replace("_", "-")
    _seed_decision(dec_workspace, decision_id, status=from_status)
    gateway = CommandGateway(dec_workspace)
    auth_id = f"HAUTH-{decision_id}"
    receipt, exit_code = gateway.execute_command(
        _resolve_decision_envelope(
            decision_id,
            expected_revision=1,
            to_status=to_status,
            auth_id=auth_id,
        )
    )
    assert exit_code == 0, receipt
    updated = yaml.safe_load(
        (dec_workspace.ai_team / "decisions" / f"{decision_id}.yaml").read_text(encoding="utf-8")
    )
    assert updated["status"] == to_status
    assert updated["revision"] == 2
    auth_record = json.loads(
        (dec_workspace.ai_team / "authorizations" / f"{auth_id}.json").read_text(encoding="utf-8")
    )
    assert auth_record["consumed_at"]


RESOLVABLE_TARGETS = frozenset({"decided", "cancelled"})


FORBIDDEN_RESOLVE_TRANSITIONS = [
    (from_status, to_status)
    for from_status, to_status in iter_forbidden_transitions()
    if from_status in {"decided", "cancelled"} and to_status in RESOLVABLE_TARGETS
]


@pytest.mark.parametrize("from_status,to_status", FORBIDDEN_RESOLVE_TRANSITIONS)
def test_forbidden_decision_transitions_rejected(
    dec_workspace: Workspace, from_status: str, to_status: str
) -> None:
    decision_id = f"DEC-FORB-{from_status}-{to_status}".replace("_", "-")
    _seed_decision(dec_workspace, decision_id, status=from_status)
    before = (dec_workspace.ai_team / "decisions" / f"{decision_id}.yaml").read_text(
        encoding="utf-8"
    )
    gateway = CommandGateway(dec_workspace)
    receipt, exit_code = gateway.execute_command(
        _resolve_decision_envelope(
            decision_id,
            expected_revision=1,
            to_status=to_status,
            auth_id=f"HAUTH-{decision_id}",
        )
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_TRANSITION.value
    after = (dec_workspace.ai_team / "decisions" / f"{decision_id}.yaml").read_text(
        encoding="utf-8"
    )
    assert before == after


def test_resolve_preserves_question_and_options(dec_workspace: Workspace) -> None:
    _seed_decision(dec_workspace, "DEC-PRESERVE", status="pending_human")
    gateway = CommandGateway(dec_workspace)
    gateway.execute_command(
        _resolve_decision_envelope("DEC-PRESERVE", expected_revision=1, to_status="decided")
    )
    updated = yaml.safe_load(
        (dec_workspace.ai_team / "decisions" / "DEC-PRESERVE.yaml").read_text(encoding="utf-8")
    )
    assert updated["question"] == "Which option?"
    assert updated["options"] == [
        {"id": "a", "label": "Option A"},
        {"id": "b", "label": "Option B"},
    ]


def test_register_finding_via_gateway(dec_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-find-001",
        "idempotency_key": "idem-find-001",
        "correlation_id": "COR-find-001",
        "type": "RegisterFinding",
        "issued_at": "2026-08-29T17:47:00Z",
        "actor": _auditor_actor(),
        "target": {"kind": "finding", "id": "FIND-001"},
        "payload": {
            "id": "FIND-001",
            "work_unit": "WU-FIND-REF",
            "severity": "medium",
            "classification": "expected_and_observed",
            "claim": "Test finding claim.",
            "evidence": ["EV-test"],
            "limitations": [],
            "status": "open",
        },
    }
    gateway = CommandGateway(dec_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    assert (dec_workspace.ai_team / "findings" / "FIND-001.yaml").is_file()
    work_unit = yaml.safe_load(
        (dec_workspace.ai_team / "work-units" / "WU-FIND-REF.yaml").read_text(encoding="utf-8")
    )
    assert "FIND-001" in work_unit["outcomes"]["audit_findings"]


def test_register_finding_rejects_duplicate(dec_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-find-dup",
        "idempotency_key": "idem-find-dup-1",
        "correlation_id": "COR-find-dup",
        "type": "RegisterFinding",
        "issued_at": "2026-08-29T17:47:00Z",
        "actor": _auditor_actor(),
        "target": {"kind": "finding", "id": "FIND-DUP"},
        "payload": {
            "id": "FIND-DUP",
            "severity": "low",
            "classification": "unknown",
            "claim": "Duplicate test.",
            "evidence": [],
            "limitations": [],
            "status": "open",
        },
    }
    gateway = CommandGateway(dec_workspace)
    gateway.execute_command(envelope)
    retry = dict(envelope)
    retry["idempotency_key"] = "idem-find-dup-2"
    retry["command_id"] = "CMD-find-dup-2"
    receipt, exit_code = gateway.execute_command(retry)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.ALREADY_EXISTS.value
