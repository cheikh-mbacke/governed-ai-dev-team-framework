"""WU-P3-GW-OBS-EVID — RecordObservation and RegisterEvidence gateway handlers."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.persistence.lock import force_release_stale_lock
from governed_ai.core.workspace import Workspace

from tests.core.workspace_helpers import FABRIC_ROOT, PAYLOAD_AI_TEAM, write_installed_client_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def obs_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="framework-renov")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    shutil.copytree(source / "contracts", ai_team / "contracts")
    for directory in ("observations", "evidence", "work-units", "state"):
        (ai_team / directory).mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text(
        yaml.safe_dump(
            {
                "project_id": "framework-renov",
                "constitution_version": "1.1.0",
                "phase": "execution",
            }
        ),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _base_envelope(**overrides) -> dict:
    base = {
        "protocol_version": "1.0",
        "command_id": "CMD-obs-001",
        "idempotency_key": "idem-obs-001",
        "correlation_id": "COR-obs-001",
        "type": "RecordObservation",
        "issued_at": "2026-08-29T17:00:00Z",
        "actor": {
            "kind": "role",
            "execution_id": "EXE-obs",
            "role_id": "code-reviewer",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        "target": {"kind": "observation", "id": "OBS-TEST-001"},
        "payload": {
            "id": "OBS-TEST-001",
            "category": "tooling",
            "symptom": "Gateway mediated observation from readonly role",
            "classification": {"origin": "unknown", "confidence": "low"},
            "impact": {
                "blocked_minutes": 0,
                "rework_required": False,
                "human_intervention": False,
                "affected_work_units": [],
            },
        },
    }
    base.update(overrides)
    return base


def test_record_observation_via_gateway_readonly_role(obs_workspace: Workspace) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    receipt, exit_code = gateway.execute_command(_base_envelope(idempotency_key="idem-obs-a"))
    assert exit_code == 0
    assert receipt["status"] == "accepted"
    assert receipt["affected"][0]["coalesced"] is False
    assert receipt["affected"][0]["occurrence_count"] == 1
    path = obs_workspace.ai_team / "observations" / "OBS-TEST-001.yaml"
    assert path.is_file()
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["symptom"] == "Gateway mediated observation from readonly role"
    assert saved["recorded_by"] == "code-reviewer"
    assert saved["occurrence_count"] == 1
    assert saved["last_recorded_at"] == saved["recorded_at"]


def test_record_observation_coalesces_on_recurrence_key(obs_workspace: Workspace) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    first = _base_envelope(
        command_id="CMD-obs-coal-1",
        idempotency_key="idem-obs-coal-1",
        target={"kind": "observation", "id": "OBS-COAL-001"},
        payload={
            "id": "OBS-COAL-001",
            "category": "tooling",
            "symptom": "first sighting",
            "severity": "low",
            "classification": {"origin": "framework", "confidence": "low"},
            "impact": {
                "blocked_minutes": 5,
                "rework_required": False,
                "human_intervention": False,
                "affected_work_units": [],
            },
            "evidence_refs": ["EV-1"],
            "recurrence_key": "missing-allowlist-entry",
        },
    )
    receipt1, exit1 = gateway.execute_command(first)
    assert exit1 == 0
    assert receipt1["affected"][0]["coalesced"] is False

    second = _base_envelope(
        command_id="CMD-obs-coal-2",
        idempotency_key="idem-obs-coal-2",
        target={"kind": "observation", "id": "new"},
        payload={
            "category": "tooling",
            "symptom": "second sighting ignored for symptom",
            "severity": "high",
            "classification": {"origin": "framework", "confidence": "probable"},
            "impact": {
                "blocked_minutes": 10,
                "rework_required": True,
                "human_intervention": False,
                "affected_work_units": [],
            },
            "evidence_refs": ["EV-2"],
            "recurrence_key": "missing-allowlist-entry",
        },
    )
    receipt2, exit2 = gateway.execute_command(second)
    assert exit2 == 0
    assert receipt2["affected"][0]["id"] == "OBS-COAL-001"
    assert receipt2["affected"][0]["coalesced"] is True
    assert receipt2["affected"][0]["occurrence_count"] == 2

    paths = list((obs_workspace.ai_team / "observations").glob("*.yaml"))
    assert len(paths) == 1
    saved = yaml.safe_load(paths[0].read_text(encoding="utf-8"))
    assert saved["id"] == "OBS-COAL-001"
    assert saved["symptom"] == "first sighting"
    assert saved["severity"] == "high"
    assert saved["occurrence_count"] == 2
    assert saved["impact"]["blocked_minutes"] == 15
    assert saved["impact"]["rework_required"] is True
    assert sorted(saved["evidence_refs"]) == ["EV-1", "EV-2"]
    assert saved["last_recorded_at"] != saved["recorded_at"]


def test_record_observation_same_key_different_work_unit_does_not_coalesce(
    obs_workspace: Workspace,
) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    (obs_workspace.ai_team / "work-units" / "WU-A.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-A",
                "title": "A",
                "objective": {"result": "a"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "a",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
                "status": "ready",
            }
        ),
        encoding="utf-8",
    )
    (obs_workspace.ai_team / "work-units" / "WU-B.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-B",
                "title": "B",
                "objective": {"result": "b"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "b",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
                "status": "ready",
            }
        ),
        encoding="utf-8",
    )
    gateway = CommandGateway(obs_workspace)
    for index, work_unit in enumerate(("WU-A", "WU-B"), start=1):
        receipt, exit_code = gateway.execute_command(
            _base_envelope(
                command_id=f"CMD-obs-wu-{index}",
                idempotency_key=f"idem-obs-wu-{index}",
                target={"kind": "observation", "id": f"OBS-WU-{index}"},
                payload={
                    "id": f"OBS-WU-{index}",
                    "category": "orchestration",
                    "symptom": f"friction on {work_unit}",
                    "classification": {"origin": "unknown", "confidence": "low"},
                    "work_unit": work_unit,
                    "impact": {
                        "blocked_minutes": 0,
                        "rework_required": False,
                        "human_intervention": False,
                        "affected_work_units": [work_unit],
                    },
                    "recurrence_key": "auto:implementation:failed",
                },
            )
        )
        assert exit_code == 0, receipt
        assert receipt["affected"][0]["coalesced"] is False
    assert len(list((obs_workspace.ai_team / "observations").glob("*.yaml"))) == 2


def test_record_observation_after_resolved_starts_new_episode(
    obs_workspace: Workspace,
) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    first, exit1 = gateway.execute_command(
        _base_envelope(
            command_id="CMD-obs-res-1",
            idempotency_key="idem-obs-res-1",
            target={"kind": "observation", "id": "OBS-RES-001"},
            payload={
                "id": "OBS-RES-001",
                "category": "tooling",
                "symptom": "resolved episode",
                "classification": {"origin": "framework", "confidence": "high"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
                "recurrence_key": "flake-gate",
                "status": "resolved",
                "resolution": "fixed in patch",
            },
        )
    )
    assert exit1 == 0
    assert first["affected"][0]["coalesced"] is False

    second, exit2 = gateway.execute_command(
        _base_envelope(
            command_id="CMD-obs-res-2",
            idempotency_key="idem-obs-res-2",
            target={"kind": "observation", "id": "OBS-RES-002"},
            payload={
                "id": "OBS-RES-002",
                "category": "tooling",
                "symptom": "came back",
                "classification": {"origin": "framework", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
                "recurrence_key": "flake-gate",
            },
        )
    )
    assert exit2 == 0
    assert second["affected"][0]["id"] == "OBS-RES-002"
    assert second["affected"][0]["coalesced"] is False
    assert len(list((obs_workspace.ai_team / "observations").glob("*.yaml"))) == 2


def _control_plane_actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-obs-cp",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def test_transition_observation_open_to_acknowledged(obs_workspace: Workspace) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    created, exit_code = gateway.execute_command(
        _base_envelope(
            command_id="CMD-obs-tr-create",
            idempotency_key="idem-obs-tr-create",
            target={"kind": "observation", "id": "OBS-TR-001"},
            payload={
                "id": "OBS-TR-001",
                "category": "tooling",
                "symptom": "needs triage",
                "classification": {"origin": "unknown", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
            },
        )
    )
    assert exit_code == 0, created

    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-obs-tr-ack",
            "idempotency_key": "idem-obs-tr-ack",
            "correlation_id": "COR-obs-tr-ack",
            "type": "TransitionObservation",
            "issued_at": "2026-08-29T17:10:00Z",
            "actor": _control_plane_actor(),
            "target": {
                "kind": "observation",
                "id": "OBS-TR-001",
                "expected_revision": 1,
            },
            "payload": {
                "to_status": "acknowledged",
                "classification": {"origin": "framework", "confidence": "probable"},
            },
        }
    )
    assert exit_code == 0, receipt
    assert receipt["affected"][0]["status"] == "acknowledged"
    assert receipt["affected"][0]["from_status"] == "open"
    assert receipt["affected"][0]["revision"] == 2
    saved = yaml.safe_load(
        (obs_workspace.ai_team / "observations" / "OBS-TR-001.yaml").read_text(encoding="utf-8")
    )
    assert saved["status"] == "acknowledged"
    assert saved["classification"] == {"origin": "framework", "confidence": "probable"}
    assert saved["revision"] == 2


def test_transition_observation_requires_resolution_for_terminal(
    obs_workspace: Workspace,
) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    gateway.execute_command(
        _base_envelope(
            command_id="CMD-obs-tr-term-create",
            idempotency_key="idem-obs-tr-term-create",
            target={"kind": "observation", "id": "OBS-TR-002"},
            payload={
                "id": "OBS-TR-002",
                "category": "tooling",
                "symptom": "close me",
                "classification": {"origin": "framework", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
            },
        )
    )
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-obs-tr-term",
            "idempotency_key": "idem-obs-tr-term",
            "correlation_id": "COR-obs-tr-term",
            "type": "TransitionObservation",
            "issued_at": "2026-08-29T17:10:00Z",
            "actor": _control_plane_actor(),
            "target": {
                "kind": "observation",
                "id": "OBS-TR-002",
                "expected_revision": 1,
            },
            "payload": {"to_status": "resolved"},
        }
    )
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVALID_SCHEMA.value


def test_transition_observation_resolved_then_rejects_further_change(
    obs_workspace: Workspace,
) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    gateway.execute_command(
        _base_envelope(
            command_id="CMD-obs-tr-res-create",
            idempotency_key="idem-obs-tr-res-create",
            target={"kind": "observation", "id": "OBS-TR-003"},
            payload={
                "id": "OBS-TR-003",
                "category": "tooling",
                "symptom": "done",
                "classification": {"origin": "framework", "confidence": "confirmed"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
            },
        )
    )
    ok, exit_ok = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-obs-tr-res",
            "idempotency_key": "idem-obs-tr-res",
            "correlation_id": "COR-obs-tr-res",
            "type": "TransitionObservation",
            "issued_at": "2026-08-29T17:10:00Z",
            "actor": _control_plane_actor(),
            "target": {
                "kind": "observation",
                "id": "OBS-TR-003",
                "expected_revision": 1,
            },
            "payload": {"to_status": "resolved", "resolution": "shipped fix"},
        }
    )
    assert exit_ok == 0, ok
    assert ok["affected"][0]["revision"] == 2

    bad, exit_bad = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-obs-tr-res-again",
            "idempotency_key": "idem-obs-tr-res-again",
            "correlation_id": "COR-obs-tr-res-again",
            "type": "TransitionObservation",
            "issued_at": "2026-08-29T17:11:00Z",
            "actor": _control_plane_actor(),
            "target": {
                "kind": "observation",
                "id": "OBS-TR-003",
                "expected_revision": 2,
            },
            "payload": {"to_status": "acknowledged"},
        }
    )
    assert exit_bad == 3
    assert bad["errors"][0]["code"] == ErrorCode.INVALID_TRANSITION.value


def test_transition_observation_revision_conflict(obs_workspace: Workspace) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    gateway.execute_command(
        _base_envelope(
            command_id="CMD-obs-tr-cf-create",
            idempotency_key="idem-obs-tr-cf-create",
            target={"kind": "observation", "id": "OBS-TR-004"},
            payload={
                "id": "OBS-TR-004",
                "category": "tooling",
                "symptom": "conflict",
                "classification": {"origin": "unknown", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
            },
        )
    )
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-obs-tr-cf",
            "idempotency_key": "idem-obs-tr-cf",
            "correlation_id": "COR-obs-tr-cf",
            "type": "TransitionObservation",
            "issued_at": "2026-08-29T17:10:00Z",
            "actor": _control_plane_actor(),
            "target": {
                "kind": "observation",
                "id": "OBS-TR-004",
                "expected_revision": 99,
            },
            "payload": {"to_status": "acknowledged"},
        }
    )
    assert exit_code == 5
    assert receipt["errors"][0]["code"] == ErrorCode.CONFLICT.value


def test_register_evidence_create_exclusive(obs_workspace: Workspace) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    envelope = _base_envelope(
        command_id="CMD-ev-001",
        idempotency_key="idem-ev-a",
        type="RegisterEvidence",
        actor={
            "kind": "role",
            "execution_id": "EXE-ev",
            "role_id": "qa-test",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        target={"kind": "evidence", "id": "EV-TEST-001"},
        payload={
            "id": "EV-TEST-001",
            "type": "test_execution",
            "command_or_observation": "python -m pytest tests/core/ -q",
            "result": {"status": "pass"},
            "demonstrates": ["handler works"],
            "limitations": [],
        },
    )
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    assert receipt["affected"][0]["kind"] == "evidence"
    path = obs_workspace.ai_team / "evidence" / "EV-TEST-001.yaml"
    assert path.is_file()


def test_cg011_update_evidence_rejected(obs_workspace: Workspace) -> None:
    gateway = CommandGateway(obs_workspace)
    envelope = _base_envelope(
        type="UpdateEvidence",
        target={"kind": "evidence", "id": "EV-TEST-001"},
        payload={"id": "EV-TEST-001", "result": {"status": "pass"}},
    )
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 6
    assert receipt["errors"][0]["code"] == ErrorCode.UNSUPPORTED_CONTRACT.value


def test_cg011_duplicate_evidence_rejected(obs_workspace: Workspace) -> None:
    force_release_stale_lock(obs_workspace.ai_team / "locks" / "project.lock")
    gateway = CommandGateway(obs_workspace)
    envelope = _base_envelope(
        command_id="CMD-ev-dup",
        idempotency_key="idem-ev-dup",
        type="RegisterEvidence",
        actor={
            "kind": "role",
            "execution_id": "EXE-ev",
            "role_id": "backend-developer",
            "bundle_version": "1.0.0",
            "adapter_id": "cursor",
        },
        target={"kind": "evidence", "id": "EV-DUP-001"},
        payload={
            "id": "EV-DUP-001",
            "type": "test_execution",
            "command_or_observation": "pytest",
            "result": {"status": "pass"},
            "demonstrates": ["first"],
            "limitations": [],
        },
    )
    gateway.execute_command(envelope)
    before = (obs_workspace.ai_team / "evidence" / "EV-DUP-001.yaml").read_text(encoding="utf-8")
    envelope["idempotency_key"] = "idem-ev-dup-2"
    envelope["payload"] = {**envelope["payload"], "demonstrates": ["changed"]}
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.ALREADY_EXISTS.value
    after = (obs_workspace.ai_team / "evidence" / "EV-DUP-001.yaml").read_text(encoding="utf-8")
    assert before == after
