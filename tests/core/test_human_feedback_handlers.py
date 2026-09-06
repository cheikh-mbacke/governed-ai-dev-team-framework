"""Asynchronous formative human UI feedback gateway tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from tests.core.workspace_helpers import PAYLOAD_AI_TEAM, write_installed_client_profile

from governed_ai.core.commands.errors import ErrorCode
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.run.autonomy_policy import resolve_effective_policy
from governed_ai.core.workspace import Workspace

SHA_OBSERVED = "a" * 40
SHA_CURRENT = "b" * 40


@pytest.fixture()
def feedback_workspace(tmp_path: Path) -> Workspace:
    ai_team = tmp_path / ".ai-team"
    for name in ("schemas", "constitution", "contracts"):
        shutil.copytree(PAYLOAD_AI_TEAM / name, ai_team / name)
    write_installed_client_profile(ai_team, project_id="human-feedback-test")
    for directory in (
        "authorizations",
        "decisions",
        "events",
        "human-feedback",
        "work-units",
    ):
        (ai_team / directory).mkdir(parents=True, exist_ok=True)
    (ai_team / "work-units" / "WU-UI-001.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "WU-UI-001",
                "title": "Dashboard",
                "objective": {"result": "Show the dashboard"},
                "scope": {"include": ["dashboard"], "exclude": []},
                "zone": {"area": "frontend", "capabilities": [], "components": []},
                "expected_behavior": "The dashboard is usable",
                "acceptance_criteria": ["Dashboard renders"],
                "dependencies": [],
                "risk": {"class": "medium", "reasons": []},
                "required_verification": {"qa": True, "review": True},
                "human_ui_review": {
                    "required": True,
                    "reason": "first_testable_slice",
                    "surface": "dashboard",
                    "planned_after": "qa",
                    "blocking_behavior": "non_blocking",
                },
                "status": "review",
                "revision": 3,
                "created_at": "2026-09-06T08:00:00Z",
                "updated_at": "2026-09-06T08:00:00Z",
                "events": [],
                "evidence": ["EV-QA-001"],
                "outcomes": {
                    "review_status": "pending",
                    "audit_status": "not_required",
                    "critical_open_items": [],
                    "defects": [],
                    "audit_findings": [],
                    "human_acceptance": None,
                    "human_feedback": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (ai_team / "events" / "EVT-UI-CHECKPOINT.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "EVT-UI-CHECKPOINT",
                "type": "HANDOFF",
                "work_unit": "WU-UI-001",
                "summary": "Dashboard ready for human observation",
                "status": "open",
                "details": {
                    "human_checkpoint": {
                        "command": "http://localhost:3000/dashboard",
                        "why": "First coherent dashboard slice",
                        "surface": "dashboard",
                        "observed_revision": SHA_OBSERVED,
                        "acceptance_package_ref": ".ai-team/acceptance/UAT-UI-001.yaml",
                        "non_blocking": True,
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return Workspace.from_root(tmp_path)


def _actor() -> dict:
    return {
        "kind": "role",
        "execution_id": "EXE-human-feedback",
        "role_id": "control-plane",
        "bundle_version": "1.0.0",
        "adapter_id": "cursor",
    }


def _record_envelope(*, include_auth: bool = True) -> dict:
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-HF-RECORD-001",
        "idempotency_key": "idem-hf-record-001",
        "correlation_id": "COR-HF-001",
        "type": "RecordHumanFeedback",
        "issued_at": "2026-09-06T09:00:00Z",
        "actor": _actor(),
        "target": {"kind": "human_feedback", "id": "HF-UI-001"},
        "payload": {
            "id": "HF-UI-001",
            "checkpoint_ref": "EVT-UI-CHECKPOINT",
            "acceptance_package_ref": ".ai-team/acceptance/UAT-UI-001.yaml",
            "work_unit": "WU-UI-001",
            "surface": "dashboard",
            "observed_revision": {
                "commit_sha": SHA_OBSERVED,
                "captured_at": "2026-09-06T08:30:00Z",
                "evidence_refs": ["EV-QA-001"],
            },
            "scenario_results": [
                {"scenario_id": "UI-01", "result": "failed", "notes": "CTA unclear"}
            ],
            "comment": "The primary action is difficult to identify.",
            "submitted_by": "product-owner",
        },
    }
    if include_auth:
        envelope["human_authorization"] = {
            "authorization_id": "HAUTH-HF-001",
            "granted_by": "product-owner",
            "granted_at": "2026-09-06T09:00:00Z",
            "scope": "human-feedback:HF-UI-001",
            "consumed_at": None,
        }
    return envelope


def test_record_human_feedback_is_non_blocking_and_closes_checkpoint(
    feedback_workspace: Workspace,
) -> None:
    gateway = CommandGateway(feedback_workspace)
    receipt, exit_code = gateway.execute_command(_record_envelope())

    assert exit_code == 0
    assert receipt["details"]["non_blocking"] is True
    feedback = yaml.safe_load(
        (feedback_workspace.ai_team / "human-feedback" / "HF-UI-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert feedback["status"] == "pending_reconciliation"
    assert feedback["observed_revision"]["commit_sha"] == SHA_OBSERVED

    work_unit = yaml.safe_load(
        (feedback_workspace.ai_team / "work-units" / "WU-UI-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert work_unit["status"] == "review"
    assert work_unit["revision"] == 4
    assert work_unit["outcomes"]["human_feedback"] == ["HF-UI-001"]

    checkpoint = yaml.safe_load(
        (feedback_workspace.ai_team / "events" / "EVT-UI-CHECKPOINT.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["status"] == "closed"
    assert checkpoint["details"]["human_feedback_ref"] == "HF-UI-001"


def test_record_human_feedback_requires_human_authorization(
    feedback_workspace: Workspace,
) -> None:
    receipt, exit_code = CommandGateway(feedback_workspace).execute_command(
        _record_envelope(include_auth=False)
    )
    assert exit_code == 4
    assert receipt["errors"][0]["code"] == ErrorCode.HUMAN_AUTH_REQUIRED.value
    assert not (feedback_workspace.ai_team / "human-feedback" / "HF-UI-001.yaml").exists()


def test_reconcile_human_feedback_traces_remediation_without_rewriting_old_evidence(
    feedback_workspace: Workspace,
) -> None:
    gateway = CommandGateway(feedback_workspace)
    assert gateway.execute_command(_record_envelope())[1] == 0
    source = yaml.safe_load(
        (feedback_workspace.ai_team / "work-units" / "WU-UI-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    remediation = dict(source)
    remediation.update(
        {
            "id": "WU-UI-REMEDIATION-001",
            "title": "Clarify dashboard primary action",
            "status": "ready",
            "revision": 1,
            "evidence": [],
        }
    )
    remediation["outcomes"] = {
        "review_status": "pending",
        "audit_status": "not_required",
        "critical_open_items": [],
        "defects": [],
        "audit_findings": [],
        "human_acceptance": None,
        "human_feedback": ["HF-UI-001"],
    }
    (feedback_workspace.ai_team / "work-units" / "WU-UI-REMEDIATION-001.yaml").write_text(
        yaml.safe_dump(remediation, sort_keys=False), encoding="utf-8"
    )

    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-HF-RECONCILE-001",
        "idempotency_key": "idem-hf-reconcile-001",
        "correlation_id": "COR-HF-001",
        "type": "ReconcileHumanFeedback",
        "issued_at": "2026-09-06T09:05:00Z",
        "actor": _actor(),
        "target": {"kind": "human_feedback", "id": "HF-UI-001", "expected_revision": 1},
        "payload": {
            "to_status": "reconciled",
            "reconciliation": {
                "classification": "ux_adjustment",
                "applicability": "applicable",
                "current_code_revision": SHA_CURRENT,
                "affected_work_units": ["WU-UI-001", "WU-UI-REMEDIATION-001"],
                "invalidated_evidence": ["EV-QA-001"],
                "actions": [
                    {
                        "kind": "remediation_work_unit",
                        "ref": "WU-UI-REMEDIATION-001",
                        "reason": "Apply the human UX feedback on current code",
                    }
                ],
                "rationale": "The issue remains present after comparing both revisions.",
            },
        },
    }
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 0
    assert receipt["details"]["invalidated_evidence"] == ["EV-QA-001"]
    feedback = yaml.safe_load(
        (feedback_workspace.ai_team / "human-feedback" / "HF-UI-001.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert feedback["status"] == "reconciled"
    assert feedback["reconciliation"]["actions"][0]["ref"] == "WU-UI-REMEDIATION-001"
    assert feedback["reconciliation"]["reconciled_by_role"] == "control-plane"


def test_reconcile_applicable_change_requires_traced_action(
    feedback_workspace: Workspace,
) -> None:
    gateway = CommandGateway(feedback_workspace)
    assert gateway.execute_command(_record_envelope())[1] == 0
    envelope = {
        "protocol_version": "1.0",
        "command_id": "CMD-HF-RECONCILE-NO-ACTION",
        "idempotency_key": "idem-hf-reconcile-no-action",
        "correlation_id": "COR-HF-001",
        "type": "ReconcileHumanFeedback",
        "issued_at": "2026-09-06T09:05:00Z",
        "actor": _actor(),
        "target": {"kind": "human_feedback", "id": "HF-UI-001", "expected_revision": 1},
        "payload": {
            "to_status": "reconciled",
            "reconciliation": {
                "classification": "defect",
                "applicability": "applicable",
                "current_code_revision": SHA_CURRENT,
                "affected_work_units": ["WU-UI-001"],
                "invalidated_evidence": ["EV-QA-001"],
                "actions": [],
                "rationale": "Still reproducible.",
            },
        },
    }
    receipt, exit_code = gateway.execute_command(envelope)
    assert exit_code == 3
    assert receipt["errors"][0]["code"] == ErrorCode.INVARIANT_VIOLATION.value


@pytest.mark.parametrize(
    "preset",
    ["unattended_conservative", "unattended_extended", "unattended_maximal"],
)
def test_unattended_profiles_keep_formative_checkpoints_non_blocking(preset: str) -> None:
    policy = resolve_effective_policy(preset)
    assert policy["human_feedback"] == {
        "visual_checkpoints": "non_blocking",
        "pending_feedback_behavior": "reconcile_before_next_affected_dispatch",
        "continue_unaffected_work": True,
        "may_reduce_execution_ceiling": False,
    }
