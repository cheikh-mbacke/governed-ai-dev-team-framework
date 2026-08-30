"""Pre-execution guards for Cursor runtime harness (AD-006–AD-010)."""

from __future__ import annotations

from typing import Any

from governed_ai.adapters.spi import ExecutionRequest, RoleDefinitionRevision

PRODUCT_WRITE_COMMANDS = frozenset(
    {
        "CreateWorkUnit",
        "TransitionWorkUnit",
        "RegisterEvidence",
        "RegisterFinding",
        "CreateDecisionRequest",
        "ResolveDecisionRequest",
        "RecordGateDecision",
        "RegisterReleaseCandidate",
        "RecordAcceptance",
    }
)
GATE_COMMANDS = frozenset({"RecordGateDecision", "RecordAcceptance"})
MEDIATED_SIGNAL_COMMANDS = frozenset({"RecordObservation"})


class ExecutionGuardError(Exception):
    """Raised when a runtime request would violate adapter authority boundaries."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class UnsupportedContractError(ExecutionGuardError):
    """CT-008 — protocol/platform/bundle negotiation failed."""


class CapabilityNotEnforceableError(ExecutionGuardError):
    """CT-009 — required capability cannot be guaranteed."""


def _command_entries(request: ExecutionRequest) -> list[dict[str, Any]]:
    raw = request.get("requested_commands") or []
    entries: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            entries.append(item)
    return entries


def validate_requested_commands(
    request: ExecutionRequest,
    role: RoleDefinitionRevision,
) -> None:
    """AD-006/007/008 — reject authority-expanding requested commands."""
    product_level = role.get("writes", {}).get("product", {}).get("level", "none")
    allowed_governance = set(role.get("writes", {}).get("authoritative_governance_commands") or [])
    allowed_signals = set(role.get("writes", {}).get("non_authoritative_signal_commands") or [])

    for entry in _command_entries(request):
        command_type = str(entry.get("type", ""))
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}

        if command_type in GATE_COMMANDS:
            auth = payload.get("human_authorization")
            if not isinstance(auth, dict) or not auth.get("authorization_id"):
                raise ExecutionGuardError(
                    "HUMAN_AUTH_REQUIRED",
                    f"{command_type} requires human_authorization",
                )

        if product_level == "none" and command_type in PRODUCT_WRITE_COMMANDS:
            if command_type not in allowed_governance and command_type not in allowed_signals:
                raise ExecutionGuardError(
                    "READONLY_PRODUCT_WRITE_FORBIDDEN",
                    f"readonly role cannot request {command_type}",
                )

        if command_type == "WriteProductFile":
            raise ExecutionGuardError(
                "READONLY_PRODUCT_WRITE_FORBIDDEN",
                "direct product file writes must not appear in requested_commands",
            )

        if command_type in MEDIATED_SIGNAL_COMMANDS:
            if command_type not in allowed_signals:
                raise ExecutionGuardError(
                    "UNMEDIATED_SIGNAL",
                    f"{command_type} not permitted for role",
                )
            if entry.get("mediated") is not True:
                raise ExecutionGuardError(
                    "UNMEDIATED_SIGNAL",
                    f"{command_type} must be mediated via Command Gateway",
                )
