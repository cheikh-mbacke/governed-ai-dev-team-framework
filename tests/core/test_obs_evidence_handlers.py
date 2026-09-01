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

from tests.core.workspace_helpers import write_installed_client_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def obs_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = REPO_ROOT / ".ai-team"
    for name in ("schemas", "constitution"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="framework-renov")
    shutil.copy2(source / "framework-version.json", ai_team / "framework-version.json")
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
    path = obs_workspace.ai_team / "observations" / "OBS-TEST-001.yaml"
    assert path.is_file()
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["symptom"] == "Gateway mediated observation from readonly role"
    assert saved["recorded_by"] == "code-reviewer"


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
