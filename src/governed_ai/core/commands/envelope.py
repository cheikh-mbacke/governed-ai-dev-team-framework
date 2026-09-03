"""Command envelope parsing and validation."""

from __future__ import annotations

from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError

REQUIRED_ENVELOPE_FIELDS = (
    "protocol_version",
    "command_id",
    "idempotency_key",
    "correlation_id",
    "type",
    "issued_at",
    "actor",
    "target",
    "payload",
)

GATE_COMMANDS_REQUIRING_HUMAN_AUTH = frozenset(
    {
        "RecordGateDecision",
        "RecordAcceptance",
        "ResolveDecisionRequest",
        # Document 6 §8 — issuing or revoking a RunAuthorizationGrant is a
        # human act, gated the same way as a gate decision.
        "IssueRunAuthorizationGrant",
        "RevokeRunAuthorizationGrant",
    }
)

IMMUTABLE_UPDATE_COMMANDS = frozenset({"UpdateEvidence", "DeleteEvidence"})


def parse_envelope(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "command envelope must be an object", "")

    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in raw:
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"missing required field {field!r}",
                f"/{field}",
            )

    if raw["protocol_version"] != "1.0":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "unsupported protocol_version",
            "/protocol_version",
        )

    actor = raw["actor"]
    if not isinstance(actor, dict) or actor.get("kind") != "role":
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "actor.kind must be role", "/actor/kind")
    if not actor.get("role_id"):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "actor.role_id is required", "/actor/role_id")

    target = raw["target"]
    if not isinstance(target, dict) or not target.get("kind") or not target.get("id"):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "target.kind and target.id required", "/target")

    if raw["type"] in IMMUTABLE_UPDATE_COMMANDS:
        raise GatewayError(
            ErrorCode.UNSUPPORTED_CONTRACT,
            f"{raw['type']} is not supported; evidence is create-exclusive",
            "/type",
        )

    if raw["type"] == "CreateWorkUnit":
        _validate_create_work_unit(raw)
    elif raw["type"] == "TransitionWorkUnit":
        _validate_transition_work_unit(raw)
    elif raw["type"] == "RecordObservation":
        _validate_record_observation(raw)
    elif raw["type"] == "TransitionObservation":
        _validate_transition_observation(raw)
    elif raw["type"] == "RegisterEvidence":
        _validate_register_evidence(raw)
    elif raw["type"] == "CreateDecisionRequest":
        _validate_create_decision_request(raw)
    elif raw["type"] == "ResolveDecisionRequest":
        _validate_resolve_decision_request(raw)
    elif raw["type"] == "RegisterFinding":
        _validate_register_finding(raw)
    elif raw["type"] == "RecordGateDecision":
        _validate_record_gate_decision(raw)
    elif raw["type"] == "RecordAcceptance":
        _validate_record_acceptance(raw)
    elif raw["type"] == "RegisterReleaseCandidate":
        _validate_register_release_candidate(raw)
    elif raw["type"] == "GenerateRetrospective":
        _validate_generate_retrospective(raw)
    elif raw["type"] == "ReviewRetrospective":
        _validate_review_retrospective(raw)
    elif raw["type"] == "ExportFeedback":
        _validate_export_feedback(raw)
    elif raw["type"] == "SubmitFeedback":
        _validate_submit_feedback(raw)
    elif raw["type"] == "OpenRun":
        _validate_open_run(raw)
    elif raw["type"] == "AcquireWorkerLease":
        _validate_acquire_worker_lease(raw)
    elif raw["type"] == "RecordExecutionAttempt":
        _validate_record_execution_attempt(raw)
    elif raw["type"] == "WriteCheckpoint":
        _validate_write_checkpoint(raw)
    elif raw["type"] == "CloseRun":
        _validate_close_run(raw)
    elif raw["type"] == "IssueRunAuthorizationGrant":
        _validate_issue_run_authorization_grant(raw)
    elif raw["type"] == "RevokeRunAuthorizationGrant":
        _validate_revoke_run_authorization_grant(raw)
    elif raw["type"] == "ResolveRunDecision":
        _validate_resolve_run_decision(raw)
    elif raw["type"] == "TightenExecutionCeiling":
        _validate_tighten_execution_ceiling(raw)
    elif raw["type"] == "EscalateWorkUnitRisk":
        _validate_escalate_work_unit_risk(raw)
    elif raw["type"] == "RecordIntegrationMerge":
        _validate_record_integration_merge(raw)
    elif raw["type"] == "RecordWorkerHeartbeat":
        _validate_record_worker_heartbeat(raw)
    elif raw["type"] == "ReleaseWorkerLease":
        _validate_release_worker_lease(raw)
    elif raw["type"] == "RegisterMissionArtifact":
        _validate_register_mission_artifact(raw)
    elif raw["type"] == "RecordMissionArtifactChallenge":
        _validate_record_mission_artifact_challenge(raw)
    if raw["type"] in GATE_COMMANDS_REQUIRING_HUMAN_AUTH and "human_authorization" not in raw:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required",
            "/human_authorization",
        )

    return raw


def _validate_create_work_unit(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "work_unit":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "CreateWorkUnit target.kind must be work_unit",
            "/target/kind",
        )
    if "expected_revision" in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must not be set on create",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != target["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )


def _validate_transition_work_unit(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "work_unit":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "TransitionWorkUnit target.kind must be work_unit",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("to_status"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.to_status is required",
            "/payload/to_status",
        )


def _validate_record_observation(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "observation":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordObservation target.kind must be observation",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("symptom"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.symptom is required",
            "/payload/symptom",
        )


def _validate_transition_observation(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "observation":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "TransitionObservation target.kind must be observation",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("to_status"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.to_status is required",
            "/payload/to_status",
        )


def _validate_register_evidence(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "evidence":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RegisterEvidence target.kind must be evidence",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )


def _validate_create_decision_request(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "decision_request":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "CreateDecisionRequest target.kind must be decision_request",
            "/target/kind",
        )
    if "expected_revision" in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must not be set on create",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != target["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )
    if not payload.get("question"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.question is required",
            "/payload/question",
        )


def _validate_resolve_decision_request(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "decision_request":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "ResolveDecisionRequest target.kind must be decision_request",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("to_status"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.to_status is required",
            "/payload/to_status",
        )
    if "human_authorization" not in raw:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required",
            "/human_authorization",
        )


def _validate_register_finding(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "finding":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RegisterFinding target.kind must be finding",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != raw["target"]["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )


def _validate_record_gate_decision(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "gate_decision":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordGateDecision target.kind must be gate_decision",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("gate") or not payload.get("status"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.gate and payload.status are required",
            "/payload/gate",
        )
    if not payload.get("by"):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.by is required", "/payload/by")
    if "human_authorization" not in raw:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required for gate decisions",
            "/human_authorization",
        )


def _validate_record_acceptance(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "acceptance":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordAcceptance target.kind must be acceptance",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != raw["target"]["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )
    if "human_authorization" not in raw:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required",
            "/human_authorization",
        )


def _validate_register_release_candidate(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "release_candidate":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RegisterReleaseCandidate target.kind must be release_candidate",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != raw["target"]["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )


def _validate_generate_retrospective(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "retrospective":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "GenerateRetrospective target.kind must be retrospective",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or payload.get("scope") not in {"work_unit", "project"}:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.scope must be work_unit or project",
            "/payload/scope",
        )
    if payload["scope"] == "work_unit" and not payload.get("work_unit_id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.work_unit_id is required for work_unit scope",
            "/payload/work_unit_id",
        )


def _validate_review_retrospective(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "retrospective":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "ReviewRetrospective target.kind must be retrospective",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    if not isinstance(target.get("expected_revision"), int) or target["expected_revision"] < 1:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must be an integer >= 1",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")


def _validate_open_run(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "OpenRun target.kind must be run",
            "/target/kind",
        )
    if "expected_revision" in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must not be set on create",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != target["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )
    if not payload.get("work_unit_ids"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.work_unit_ids is required",
            "/payload/work_unit_ids",
        )
    # Document 6 §9.6 — a Run cannot open without an attached preflight report.
    if not isinstance(payload.get("preflight"), dict) or not payload["preflight"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.preflight is required and must be a non-empty object",
            "/payload/preflight",
        )
    # Document 6 §8 — a Run cannot open without a bound RunAuthorizationGrant.
    if not (raw.get("run_authorization") or {}).get("grant_id"):
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "run_authorization.grant_id is required to open a Run",
            "/run_authorization/grant_id",
        )


def _validate_acquire_worker_lease(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "worker_lease":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "AcquireWorkerLease target.kind must be worker_lease",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id is required",
            "/payload/id",
        )
    if payload["id"] != target["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )
    for field in ("run_id", "work_unit_id", "worker_id"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )


def _validate_record_execution_attempt(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "execution_attempt":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordExecutionAttempt target.kind must be execution_attempt",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    for field in ("run_id", "work_unit_id", "worker_lease_id", "step", "status"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )
    if not isinstance(payload.get("epoch"), int):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.epoch must be an integer",
            "/payload/epoch",
        )


def _validate_write_checkpoint(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "checkpoint":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "WriteCheckpoint target.kind must be checkpoint",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    # target.id is the work_unit_id: a checkpoint is a per-Work-Unit upsert, not a create.
    for field in ("run_id", "worker_lease_id"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )
    if not isinstance(payload.get("epoch"), int):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.epoch must be an integer",
            "/payload/epoch",
        )


def _validate_close_run(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "CloseRun target.kind must be run",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("status"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.status is required",
            "/payload/status",
        )
    # Document 6 §9.5/§11 — a Run cannot be recorded stopped/failed without
    # citing which global stop condition triggered it (validated against the
    # fixed vocabulary in the handler, not left to free text).
    if payload["status"] in {"stopped", "failed"} and not payload.get("stop_condition"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.stop_condition is required when status is stopped or failed",
            "/payload/stop_condition",
        )


def _validate_issue_run_authorization_grant(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run_authorization_grant":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "IssueRunAuthorizationGrant target.kind must be run_authorization_grant",
            "/target/kind",
        )
    if "expected_revision" in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must not be set on create",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.id is required", "/payload/id")
    if payload["id"] != target["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )
    for field in ("work_unit_ids", "excluded_actions"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required and must be non-empty",
                f"/payload/{field}",
            )
    if not payload.get("expires_at"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA, "payload.expires_at is required", "/payload/expires_at"
        )
    if not isinstance(payload.get("maximum_uses"), int) or payload["maximum_uses"] < 1:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.maximum_uses must be a positive integer",
            "/payload/maximum_uses",
        )
    if not payload.get("issuing_authority"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.issuing_authority is required",
            "/payload/issuing_authority",
        )


def _validate_revoke_run_authorization_grant(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run_authorization_grant":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RevokeRunAuthorizationGrant target.kind must be run_authorization_grant",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("reason"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA, "payload.reason is required", "/payload/reason"
        )


def _validate_register_mission_artifact(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "mission_artifact":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RegisterMissionArtifact target.kind must be mission_artifact",
            "/target/kind",
        )
    if "expected_revision" in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must not be set on create",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("id"):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.id is required", "/payload/id")
    if payload["id"] != target["id"]:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.id must match target.id",
            "/payload/id",
        )
    if not payload.get("kind"):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload.kind is required", "/payload/kind")
    if not isinstance(payload.get("content"), dict):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA, "payload.content must be an object", "/payload/content"
        )


def _validate_record_mission_artifact_challenge(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "mission_artifact":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordMissionArtifactChallenge target.kind must be mission_artifact",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("outcome"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA, "payload.outcome is required", "/payload/outcome"
        )


def _validate_resolve_run_decision(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run_decision":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "ResolveRunDecision target.kind must be run_decision",
            "/target/kind",
        )
    if "expected_revision" in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision must not be set on create",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    for field in ("run_id", "work_unit_id", "proposed_entry_id"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )
    trigger = payload.get("trigger")
    if not isinstance(trigger, dict) or not trigger.get("type"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.trigger.type is required",
            "/payload/trigger/type",
        )


def _validate_tighten_execution_ceiling(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "TightenExecutionCeiling target.kind must be run",
            "/target/kind",
        )
    if "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "expected_revision is required",
            "/target/expected_revision",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    for field in ("work_unit_id", "dimension", "new_state", "reason"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )


def _validate_escalate_work_unit_risk(raw: dict[str, Any]) -> None:
    target = raw["target"]
    if target.get("kind") != "run" or "expected_revision" not in target:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "EscalateWorkUnitRisk requires run target and expected_revision",
            "/target",
        )
    payload = raw["payload"]
    for field in ("work_unit_id", "new_risk_class", "reason"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA, f"payload.{field} is required", f"/payload/{field}"
            )


def _validate_record_integration_merge(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "integration_merge":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordIntegrationMerge target.kind must be integration_merge",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    for field in ("run_id", "work_unit_id", "worker_lease_id"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )
    if not isinstance(payload.get("epoch"), int):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.epoch must be an integer",
            "/payload/epoch",
        )
    if not isinstance(payload.get("conflict_resolution_attempts"), int):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.conflict_resolution_attempts must be an integer",
            "/payload/conflict_resolution_attempts",
        )
    if "revalidation_passed" not in payload or not isinstance(
        payload["revalidation_passed"], bool
    ):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.revalidation_passed must be a boolean",
            "/payload/revalidation_passed",
        )


def _validate_record_worker_heartbeat(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "worker_lease":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "RecordWorkerHeartbeat target.kind must be worker_lease",
            "/target/kind",
        )


def _validate_release_worker_lease(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "worker_lease":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "ReleaseWorkerLease target.kind must be worker_lease",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    for field in ("run_id", "work_unit_id"):
        if not payload.get(field):
            raise GatewayError(
                ErrorCode.INVALID_SCHEMA,
                f"payload.{field} is required",
                f"/payload/{field}",
            )
    if not isinstance(payload.get("epoch"), int):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.epoch must be an integer",
            "/payload/epoch",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict) or not payload.get("run_id"):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.run_id is required",
            "/payload/run_id",
        )
    if not isinstance(payload.get("epoch"), int):
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "payload.epoch must be an integer",
            "/payload/epoch",
        )


def _validate_export_feedback(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "feedback_export":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "ExportFeedback target.kind must be feedback_export",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
    # human_authorization is not required for Feedback Export (ADR-009:
    # installing/using the framework is acceptance).


def _validate_submit_feedback(raw: dict[str, Any]) -> None:
    if raw["target"].get("kind") != "feedback_export":
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "SubmitFeedback target.kind must be feedback_export",
            "/target/kind",
        )
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")
