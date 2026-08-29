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
    elif raw["type"] == "ExportFeedback":
        _validate_export_feedback(raw)
    elif raw["type"] in GATE_COMMANDS_REQUIRING_HUMAN_AUTH and "human_authorization" not in raw:
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
    detail_level = payload.get("detail_level", "structured")
    if detail_level == "full" and "human_authorization" not in raw:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required for full export",
            "/human_authorization",
        )
