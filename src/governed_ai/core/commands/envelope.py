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
        "ExportFeedback",
    }
)


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

    if raw["type"] == "TransitionWorkUnit":
        _validate_transition_work_unit(raw)
    elif raw["type"] == "RecordGateDecision":
        if "human_authorization" not in raw:
            raise GatewayError(
                ErrorCode.HUMAN_AUTH_REQUIRED,
                "human_authorization required for gate decisions",
                "/human_authorization",
            )
    elif raw["type"] in GATE_COMMANDS_REQUIRING_HUMAN_AUTH and "human_authorization" not in raw:
        raise GatewayError(
            ErrorCode.HUMAN_AUTH_REQUIRED,
            "human_authorization required",
            "/human_authorization",
        )

    return raw


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
