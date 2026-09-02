"""WU-P3-GW-RETRO — GenerateRetrospective and ExportFeedback gateway handlers."""

from __future__ import annotations

import json
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
def retro_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="retro-test")
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    for directory in (
        "observations",
        "retrospectives",
        "metrics",
        "work-units",
        "state",
        "authorizations",
    ):
        (ai_team / directory).mkdir(parents=True)
    (ai_team / "state" / "project-state.yaml").write_text(
        yaml.safe_dump({"project_id": "retro-test", "phase": "execution"}),
        encoding="utf-8",
    )
    (ai_team / "work-units" / "WU-RETRO-TEST.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-RETRO-TEST",
                "title": "Retro test",
                "objective": {"result": "test"},
                "scope": {"include": [], "exclude": []},
                "expected_behavior": "test",
                "acceptance_criteria": ["ok"],
                "dependencies": [],
                "risk": {"class": "low", "reasons": []},
                "required_verification": {"unit_tests": True},
                "status": "done",
            }
        ),
        encoding="utf-8",
    )
    (ai_team / "observations" / "OBS-RETRO-001.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "OBS-RETRO-001",
                "recorded_at": "2026-08-29T18:00:00+00:00",
                "project_id": "retro-test",
                "framework_version": "0.5.0",
                "constitution_version": "1.1.0",
                "work_unit": "WU-RETRO-TEST",
                "phase": "execution",
                "category": "tooling",
                "severity": "low",
                "symptom": "Test friction",
                "classification": {"origin": "framework", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                    "affected_work_units": [],
                },
                "evidence_refs": [],
                "status": "open",
            }
        ),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _control_plane_actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-retro",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _human_auth(auth_id: str = "HAUTH-export-full") -> dict:
    return {
        "authorization_id": auth_id,
        "granted_by": "test-human",
        "granted_at": "2026-08-29T18:05:00Z",
        "scope": "export:full",
        "consumed_at": None,
    }


def test_generate_retrospective_via_gateway(retro_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-retro-001",
        "idempotency_key": "idem-retro-001",
        "correlation_id": "COR-retro-001",
        "type": "GenerateRetrospective",
        "issued_at": "2026-08-29T18:05:00Z",
        "actor": _control_plane_actor(),
        "target": {"kind": "retrospective", "id": "new"},
        "payload": {"scope": "work_unit", "work_unit_id": "WU-RETRO-TEST"},
    }
    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    retro_id = receipt["affected"][0]["id"]
    assert retro_id.startswith("RET-")
    path = retro_workspace.ai_team / "retrospectives" / f"{retro_id}.yaml"
    assert path.is_file()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["scope"]["type"] == "work_unit"
    assert "OBS-RETRO-001" in document["observation_refs"]


def test_export_structured_without_human_auth(retro_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-export-structured",
        "idempotency_key": "idem-export-structured",
        "correlation_id": "COR-export-001",
        "type": "ExportFeedback",
        "issued_at": "2026-08-29T18:06:00Z",
        "actor": _control_plane_actor(),
        "target": {"kind": "feedback_export", "id": "new"},
        "payload": {"detail_level": "structured"},
    }
    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    export_path = retro_workspace.root / receipt["affected"][0]["path"]
    assert export_path.is_file()
    assert "observations" not in receipt["affected"][0]
    assert receipt["affected"][0]["observation_count"] == 1


def test_export_full_requires_human_authorization(retro_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-export-full",
        "idempotency_key": "idem-export-full-noauth",
        "correlation_id": "COR-export-002",
        "type": "ExportFeedback",
        "issued_at": "2026-08-29T18:06:00Z",
        "actor": _control_plane_actor(),
        "target": {"kind": "feedback_export", "id": "new"},
        "payload": {"detail_level": "full"},
    }
    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.HUMAN_AUTH_REQUIRED.value
    assert not list((retro_workspace.ai_team / "metrics").glob("*.json"))


def test_export_full_with_human_authorization(retro_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-export-full-auth",
        "idempotency_key": "idem-export-full-auth",
        "correlation_id": "COR-export-003",
        "type": "ExportFeedback",
        "issued_at": "2026-08-29T18:06:00Z",
        "actor": _control_plane_actor(),
        "target": {"kind": "feedback_export", "id": "new"},
        "payload": {"detail_level": "full"},
        "human_authorization": _human_auth(),
    }
    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    export_path = retro_workspace.root / receipt["affected"][0]["path"]
    document = json.loads(export_path.read_text(encoding="utf-8"))
    assert document["detail_level"] == "full"
    auth_record = json.loads(
        (retro_workspace.ai_team / "authorizations" / "HAUTH-export-full.json").read_text(
            encoding="utf-8"
        )
    )
    assert auth_record["consumed_at"]
    assert "symptom" not in str(receipt)


def test_receipt_excludes_full_export_body(retro_workspace: Workspace) -> None:
    gateway = CommandGateway(retro_workspace)
    receipt, _ = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-export-receipt",
            "idempotency_key": "idem-export-receipt",
            "correlation_id": "COR-export-004",
            "type": "ExportFeedback",
            "issued_at": "2026-08-29T18:06:00Z",
            "actor": _control_plane_actor(),
            "target": {"kind": "feedback_export", "id": "new"},
            "payload": {"detail_level": "full"},
            "human_authorization": _human_auth("HAUTH-receipt-check"),
        }
    )
    serialized = json.dumps(receipt)
    assert "Test friction" not in serialized
