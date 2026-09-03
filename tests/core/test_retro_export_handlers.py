"""WU-P3-GW-RETRO — GenerateRetrospective and ExportFeedback gateway handlers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from tests.core.workspace_helpers import (
    FABRIC_ROOT,
    PAYLOAD_AI_TEAM,
    write_installed_client_profile,
)

from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def retro_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    source = PAYLOAD_AI_TEAM
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(source / name, ai_team / name)
    write_installed_client_profile(
        ai_team, project_id="retro-test", telemetry_collection="consented_share"
    )
    shutil.copy2(FABRIC_ROOT / "framework-version.json", ai_team / "framework-version.json")
    for directory in (
        "observations",
        "retrospectives",
        "metrics",
        "work-units",
        "state",
        "authorizations",
        "runs/execution-attempts",
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
    (ai_team / "runs" / "execution-attempts" / "ATTEMPT-RETRO-001.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "ATTEMPT-RETRO-001",
                "revision": 2,
                "run_id": "RUN-RETRO-001",
                "execution_id": "EXE-RETRO-001",
                "work_unit_id": "WU-RETRO-TEST",
                "worker_lease_id": "LEASE-RETRO-001",
                "epoch": 1,
                "step": "verification",
                "status": "succeeded",
                "started_at": "2026-08-29T18:00:00+00:00",
                "ended_at": "2026-08-29T18:00:02+00:00",
                "duration_ms": 2000,
                "contract": {"role_id": "qa-test", "procedure_id": "verify-work-unit"},
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.02,
                    "currency": "USD",
                },
                "provider": {"model": "test-model"},
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
    assert document["signals"]["executions"]["total"] == 1
    assert document["signals"]["executions"]["total_tokens"] == 15


def test_export_is_full_without_human_authorization(retro_workspace: Workspace) -> None:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-export-full",
        "idempotency_key": "idem-export-full",
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
    assert receipt["affected"][0]["observation_count"] == 1
    document = json.loads(export_path.read_text(encoding="utf-8"))
    assert document["format_version"] == "1.2"
    assert document["detail_level"] == "full"
    assert document["project_id"] == "retro-test"
    assert document["observations"][0]["symptom"] == "Test friction"
    assert document["executions"][0]["duration_ms"] == 2000
    assert document["executions"][0]["usage"]["total_tokens"] == 15


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
        }
    )
    serialized = json.dumps(receipt)
    assert "Test friction" not in serialized


def test_submit_feedback_writes_local_outbox_without_url(retro_workspace: Workspace) -> None:
    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-submit-001",
            "idempotency_key": "idem-submit-001",
            "correlation_id": "COR-submit-001",
            "type": "SubmitFeedback",
            "issued_at": "2026-08-29T18:06:00Z",
            "actor": _control_plane_actor(),
            "target": {"kind": "feedback_export", "id": "new"},
            "payload": {},
        }
    )
    assert exit_code == 0, receipt
    assert receipt["affected"][0]["transmission_status"] == "local_outbox"
    export_path = retro_workspace.root / receipt["affected"][0]["path"]
    assert "outbox" in export_path.as_posix()
    document = json.loads(export_path.read_text(encoding="utf-8"))
    assert document["detail_level"] == "full"
    assert document["project_id"] == "retro-test"
    assert document["transmission"]["status"] == "local_outbox"
