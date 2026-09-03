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
    assert document["status"] == "generated"
    assert document["revision"] == 1


def test_review_retrospective_via_gateway(retro_workspace: Workspace) -> None:
    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-retro-gen-review",
            "idempotency_key": "idem-retro-gen-review",
            "correlation_id": "COR-retro-gen-review",
            "type": "GenerateRetrospective",
            "issued_at": "2026-08-29T18:05:00Z",
            "actor": _control_plane_actor(),
            "target": {"kind": "retrospective", "id": "new"},
            "payload": {"scope": "work_unit", "work_unit_id": "WU-RETRO-TEST"},
        }
    )
    assert exit_code == 0, receipt
    retro_id = receipt["affected"][0]["id"]

    review_receipt, review_exit = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-retro-review",
            "idempotency_key": "idem-retro-review",
            "correlation_id": "COR-retro-review",
            "type": "ReviewRetrospective",
            "issued_at": "2026-08-29T18:06:00Z",
            "actor": _control_plane_actor(),
            "target": {
                "kind": "retrospective",
                "id": retro_id,
                "expected_revision": 1,
            },
            "payload": {"reviewed_by": "alice", "notes": "looks good"},
        }
    )
    assert review_exit == 0, review_receipt
    assert review_receipt["affected"][0]["status"] == "reviewed"
    assert review_receipt["affected"][0]["revision"] == 2
    document = yaml.safe_load(
        (retro_workspace.ai_team / "retrospectives" / f"{retro_id}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert document["status"] == "reviewed"
    assert document["revision"] == 2
    assert document["reviewed_by"] == "alice"
    assert document["notes"] == "looks good"
    assert document["observation_refs"] == ["OBS-RETRO-001"]


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
    assert document["summary"]["occurrences"] == 1
    assert document["observations"][0]["symptom"] == "Test friction"
    assert document["executions"][0]["duration_ms"] == 2000
    assert document["executions"][0]["usage"]["total_tokens"] == 15


def test_structured_export_with_disabled_collection_validates(
    retro_workspace: Workspace,
) -> None:
    profile_path = retro_workspace.ai_team / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["telemetry"]["collection"] = "disabled"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-export-structured",
            "idempotency_key": "idem-export-structured",
            "correlation_id": "COR-export-structured",
            "type": "ExportFeedback",
            "issued_at": "2026-08-29T18:06:00Z",
            "actor": _control_plane_actor(),
            "target": {"kind": "feedback_export", "id": "new"},
            "payload": {"detail_level": "structured"},
        }
    )
    assert exit_code == 0, receipt
    export_path = retro_workspace.root / receipt["affected"][0]["path"]
    document = json.loads(export_path.read_text(encoding="utf-8"))
    assert document["detail_level"] == "structured"
    assert "project_id" not in document
    assert document["observations"][0]["occurrence_count"] == 1
    assert "observation_ref" in document["observations"][0]
    assert "symptom" not in document["observations"][0]


def test_export_schema_rejects_full_observation_without_category(
    retro_workspace: Workspace,
) -> None:
    from governed_ai.feedback import common

    document = {
        "format_version": "1.2",
        "export_id": "EXP-SCHEMA-BAD",
        "generated_at": "2026-08-29T18:06:00+00:00",
        "detail_level": "full",
        "project_ref": "PRJ-" + ("a" * 32),
        "framework_version": "0.7.0",
        "constitution_version": "1.1.0",
        "summary": {
            "total": 1,
            "open": 1,
            "occurrences": 1,
            "by_category": {"tooling": 1},
            "by_origin": {"framework": 1},
            "by_severity": {"low": 1},
            "signals": {
                "blocked_minutes": 0,
                "rework_observations": 0,
                "human_interventions": 0,
            },
            "retrospectives": 0,
            "executions": {
                "total": 0,
                "terminal": 0,
                "by_status": {},
                "by_step": {},
                "duration_ms": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost": 0,
            },
        },
        "observations": [
            {
                "id": "OBS-BAD",
                "recorded_at": "2026-08-29T18:00:00+00:00",
                "severity": "low",
                "symptom": "missing category",
                "classification": {"origin": "unknown", "confidence": "low"},
                "impact": {
                    "blocked_minutes": 0,
                    "rework_required": False,
                    "human_intervention": False,
                },
                "status": "open",
            }
        ],
        "retrospectives": [],
        "executions": [],
    }
    with pytest.raises(ValueError, match="category"):
        common.validate_payload(retro_workspace, document, "feedback-export.schema.json")


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


def test_submit_feedback_failed_transmission_lands_in_outbox(
    retro_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path = retro_workspace.ai_team / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["telemetry"]["submit_url"] = "https://feedback.example.invalid/ingest"
    profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated network failure")

    monkeypatch.setenv("GOVERNED_AI_FEEDBACK_SUBMIT_ATTEMPTS", "1")
    monkeypatch.setattr(
        "governed_ai.feedback.submit.urllib.request.urlopen",
        _boom,
    )

    gateway = CommandGateway(retro_workspace)
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": "CMD-submit-fail-001",
            "idempotency_key": "idem-submit-fail-001",
            "correlation_id": "COR-submit-fail-001",
            "type": "SubmitFeedback",
            "issued_at": "2026-08-29T18:06:00Z",
            "actor": _control_plane_actor(),
            "target": {"kind": "feedback_export", "id": "new"},
            "payload": {},
        }
    )
    assert exit_code == 0, receipt
    assert receipt["affected"][0]["transmission_status"] == "failed"
    export_path = retro_workspace.root / receipt["affected"][0]["path"]
    assert "outbox" in export_path.as_posix()
    document = json.loads(export_path.read_text(encoding="utf-8"))
    assert document["transmission"]["status"] == "failed"
    assert "simulated network failure" in (document["transmission"]["error"] or "")


def test_flush_outbox_retries_failed_export(
    retro_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from governed_ai.feedback.submit import flush_outbox

    outbox = retro_workspace.ai_team / "metrics" / "outbox"
    outbox.mkdir(parents=True)
    export_id = "EXP-FLUSH-001"
    document = {
        "format_version": "1.2",
        "export_id": export_id,
        "generated_at": "2026-08-29T18:06:00+00:00",
        "detail_level": "full",
        "project_ref": "PRJ-" + ("a" * 32),
        "project_id": "retro-test",
        "framework_version": "0.5.0",
        "constitution_version": "1.1.0",
        "summary": {
            "total": 0,
            "open": 0,
            "by_category": {},
            "by_origin": {},
            "by_severity": {},
        },
        "observations": [],
        "retrospectives": [],
        "executions": [],
        "transmission": {
            "status": "failed",
            "submitted_at": "2026-08-29T18:06:00+00:00",
            "destination": "https://feedback.example.invalid/ingest",
            "ack_id": None,
            "error": "previous failure",
        },
    }
    path = outbox / f"{export_id}.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    profile_path = retro_workspace.ai_team / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["telemetry"]["submit_url"] = "https://feedback.example.test/ingest"
    profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    class _Response:
        def read(self) -> bytes:
            return b'{"ack_id":"ACK-FLUSH-1"}'

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(
        "governed_ai.feedback.submit.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(),
    )

    results = flush_outbox(retro_workspace)
    assert len(results) == 1
    assert results[0].status == "transmitted"
    assert not path.is_file()
    archived = retro_workspace.ai_team / "metrics" / "outbox" / "transmitted" / f"{export_id}.json"
    assert archived.is_file()
    updated = json.loads(archived.read_text(encoding="utf-8"))
    assert updated["transmission"]["status"] == "transmitted"
    assert updated["transmission"]["ack_id"] == "ACK-FLUSH-1"
