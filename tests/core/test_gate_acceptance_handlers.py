"""WU-P3-GW-GATE-ACC — Gate Decision, Acceptance and Release Candidate handlers."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.workspace import Workspace

from tests.core.workspace_helpers import FABRIC_ROOT, PAYLOAD_AI_TEAM, write_installed_client_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def gate_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="gate-test")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    for directory in ("decisions", "acceptance", "release-candidates", "work-units", "state", "authorizations"):
        (ai_team / directory).mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text(
        yaml.safe_dump(
            {
                "project_id": "gate-test",
                "phase": "execution",
                "gates": {"G4": {"status": "not_required"}},
                "work_units": {
                    "WU-G4-READY": {"status": "verification"},
                    "WU-G4-BLOCKED": {"status": "verification"},
                },
            }
        ),
        encoding="utf-8",
    )
    (ai_team / "work-units" / "WU-G4-READY.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-G4-READY",
                "title": "Ready for G4",
                "objective": {"result": "test"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "test",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"review": True},
                "status": "verification",
                "evidence": ["EV-ready"],
                "outcomes": {
                    "review_status": "approved",
                    "audit_status": "not_required",
                    "critical_open_items": [],
                    "human_acceptance": None,
                },
            }
        ),
        encoding="utf-8",
    )
    (ai_team / "work-units" / "WU-G4-BLOCKED.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-G4-BLOCKED",
                "title": "Blocked for G4",
                "objective": {"result": "test"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "test",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"review": True},
                "status": "verification",
                "evidence": [],
                "outcomes": {
                    "review_status": "pending",
                    "audit_status": "not_required",
                    "critical_open_items": [],
                    "human_acceptance": None,
                },
            }
        ),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _human_auth(auth_id: str = "HAUTH-gate-001", scope: str = "gate:G4") -> dict:
    return {
        "authorization_id": auth_id,
        "granted_by": "test-human",
        "granted_at": "2026-08-29T18:00:00Z",
        "scope": scope,
        "consumed_at": None,
    }


def _gate_envelope(
    *,
    auth_id: str = "HAUTH-gate-001",
    idempotency_key: str = "idem-gate-001",
    command_id: str = "CMD-gate-001",
    **payload_overrides,
) -> dict:
    payload = {
        "gate": "G2",
        "status": "not_required",
        "by": "test-human",
        "note": "gate test",
        **payload_overrides,
    }
    return {
        "protocol_version": "1.0",
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "correlation_id": "COR-gate-001",
        "type": "RecordGateDecision",
        "issued_at": "2026-08-29T18:00:00Z",
        "actor": {
            "kind": "role",
            "execution_id": "EXE-gate",
            "role_id": "control-plane",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        "target": {"kind": "gate_decision", "id": "new"},
        "payload": payload,
        "human_authorization": _human_auth(auth_id),
    }


def test_cg007_gate_without_human_authorization(gate_workspace: Workspace) -> None:
    envelope = _gate_envelope()
    del envelope["human_authorization"]
    gateway = CommandGateway(gate_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.HUMAN_AUTH_REQUIRED.value


def test_cg008_human_authorization_reuse_rejected(gate_workspace: Workspace) -> None:
    gateway = CommandGateway(gate_workspace)
    gateway.execute_command(_gate_envelope(auth_id="HAUTH-gate-001", idempotency_key="idem-gate-cg008-a", command_id="CMD-gate-cg008-a"))
    receipt, exit_code = gateway.execute_command(
        _gate_envelope(auth_id="HAUTH-gate-001", idempotency_key="idem-gate-cg008-b", command_id="CMD-gate-cg008-b")
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.UNAUTHORIZED.value


def test_gate_decision_naming_pattern(gate_workspace: Workspace) -> None:
    gateway = CommandGateway(gate_workspace)
    receipt, exit_code = gateway.execute_command(_gate_envelope())
    assert exit_code == 0
    gate_id = receipt["affected"][0]["id"]
    assert re.match(r"^gate-g2-\d{8}T\d{12}-\w{8}$", gate_id)
    assert (gate_workspace.ai_team / "decisions" / f"{gate_id}.yaml").is_file()


def test_sm001_g4_rejected_when_preconditions_missing(gate_workspace: Workspace) -> None:
    before = (gate_workspace.ai_team / "state" / "project-state.yaml").read_text(encoding="utf-8")
    envelope = _gate_envelope(
        auth_id="HAUTH-sm001",
        idempotency_key="idem-sm001",
        gate="G4",
        status="accepted",
        work_unit_ids=["WU-G4-BLOCKED"],
    )
    gateway = CommandGateway(gate_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value
    after = (gate_workspace.ai_team / "state" / "project-state.yaml").read_text(encoding="utf-8")
    assert before == after


def test_sm002_g4_completes_with_verified_preconditions(gate_workspace: Workspace) -> None:
    gateway = CommandGateway(gate_workspace)
    receipt, exit_code = gateway.execute_command(
        _gate_envelope(
            auth_id="HAUTH-sm002",
            idempotency_key="idem-sm002",
            gate="G4",
            status="accepted",
            work_unit_ids=["WU-G4-READY"],
        )
    )
    assert exit_code == 0
    state = yaml.safe_load(
        (gate_workspace.ai_team / "state" / "project-state.yaml").read_text(encoding="utf-8")
    )
    assert state["phase"] == "completed"
    assert "preconditions_verified" in receipt["details"]
    assert receipt["details"]["preconditions_verified"][0]["work_unit_id"] == "WU-G4-READY"


def test_record_gate_updates_work_unit_on_g4(gate_workspace: Workspace) -> None:
    gateway = CommandGateway(gate_workspace)
    gateway.execute_command(
        _gate_envelope(
            auth_id="HAUTH-g4-wu",
            idempotency_key="idem-g4-wu",
            gate="G4",
            status="accepted",
            work_unit_ids=["WU-G4-READY"],
        )
    )
    work_unit = yaml.safe_load(
        (gate_workspace.ai_team / "work-units" / "WU-G4-READY.yaml").read_text(encoding="utf-8")
    )
    assert work_unit["outcomes"]["human_acceptance"] == "accepted"


def test_record_acceptance_via_gateway(gate_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-acc-001",
        "idempotency_key": "idem-acc-001",
        "correlation_id": "COR-acc-001",
        "type": "RecordAcceptance",
        "issued_at": "2026-08-29T18:01:00Z",
        "actor": {
            "kind": "role",
            "execution_id": "EXE-acc",
            "role_id": "control-plane",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        "target": {"kind": "acceptance", "id": "ACC-001"},
        "payload": {
            "id": "ACC-001",
            "scenarios": ["scenario-a"],
            "human_result": {"status": "passed"},
        },
        "human_authorization": _human_auth("HAUTH-acc-001", scope="acceptance:ACC-001"),
    }
    gateway = CommandGateway(gate_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    assert (gate_workspace.ai_team / "acceptance" / "ACC-001.yaml").is_file()


def test_register_release_candidate_via_gateway(gate_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-rc-001",
        "idempotency_key": "idem-rc-001",
        "correlation_id": "COR-rc-001",
        "type": "RegisterReleaseCandidate",
        "issued_at": "2026-08-29T18:02:00Z",
        "actor": {
            "kind": "role",
            "execution_id": "EXE-rc",
            "role_id": "release-agent",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        "target": {"kind": "release_candidate", "id": "RC-001"},
        "payload": {
            "id": "RC-001",
            "status": "draft",
            "code_revisions": ["abc123"],
            "included_work_units": ["WU-G4-READY"],
            "rollback_plan": "revert commit",
            "target_environment": "staging",
            "g3": {"status": "pending"},
        },
    }
    gateway = CommandGateway(gate_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    assert (gate_workspace.ai_team / "release-candidates" / "RC-001.yaml").is_file()
