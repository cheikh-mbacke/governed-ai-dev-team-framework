"""governed_ai.adapters.common.guard — shared authority guard (AD-006/007/008)."""

from __future__ import annotations

import pytest

from governed_ai.adapters.common.guard import ExecutionGuardError, validate_requested_commands
from governed_ai.adapters.spi import ExecutionRequest, RoleDefinitionRevision

READONLY_ROLE = RoleDefinitionRevision(
    role_id="auditor",
    writes={
        "product": {"level": "none", "paths": []},
        "authoritative_governance_commands": [],
        "non_authoritative_signal_commands": ["RecordObservation"],
    },
)

WRITE_ROLE = RoleDefinitionRevision(
    role_id="backend-developer",
    writes={
        "product": {"level": "scoped", "paths": ["<scope>"]},
        "authoritative_governance_commands": [],
        "non_authoritative_signal_commands": ["RecordObservation"],
    },
)


def _request(commands: list[dict[str, object]]) -> ExecutionRequest:
    return ExecutionRequest(requested_commands=commands)


def test_readonly_role_cannot_request_product_write_command() -> None:
    with pytest.raises(ExecutionGuardError) as excinfo:
        validate_requested_commands(
            _request([{"type": "CreateWorkUnit", "payload": {}}]),
            READONLY_ROLE,
        )
    assert excinfo.value.code == "READONLY_PRODUCT_WRITE_FORBIDDEN"


def test_write_role_may_request_product_write_command() -> None:
    validate_requested_commands(
        _request([{"type": "CreateWorkUnit", "payload": {}}]),
        WRITE_ROLE,
    )


def test_gate_command_without_human_authorization_is_rejected() -> None:
    with pytest.raises(ExecutionGuardError) as excinfo:
        validate_requested_commands(
            _request([{"type": "RecordGateDecision", "payload": {}}]),
            WRITE_ROLE,
        )
    assert excinfo.value.code == "HUMAN_AUTH_REQUIRED"


def test_gate_command_with_human_authorization_is_accepted() -> None:
    validate_requested_commands(
        _request(
            [
                {
                    "type": "RecordGateDecision",
                    "payload": {"human_authorization": {"authorization_id": "HAUTH-1"}},
                }
            ]
        ),
        WRITE_ROLE,
    )


def test_unmediated_record_observation_is_rejected() -> None:
    with pytest.raises(ExecutionGuardError) as excinfo:
        validate_requested_commands(
            _request([{"type": "RecordObservation", "payload": {}}]),
            READONLY_ROLE,
        )
    assert excinfo.value.code == "UNMEDIATED_SIGNAL"


def test_mediated_record_observation_is_accepted() -> None:
    validate_requested_commands(
        _request([{"type": "RecordObservation", "mediated": True, "payload": {}}]),
        READONLY_ROLE,
    )


def test_direct_product_file_write_always_rejected() -> None:
    with pytest.raises(ExecutionGuardError) as excinfo:
        validate_requested_commands(
            _request([{"type": "WriteProductFile", "payload": {}}]),
            WRITE_ROLE,
        )
    assert excinfo.value.code == "READONLY_PRODUCT_WRITE_FORBIDDEN"
