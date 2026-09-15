"""Pre-execution guards for Claude Code runtime harness (AD-006-010).

Re-exports the shared, tool-agnostic implementation — see
``governed_ai.adapters.common.guard``.
"""

from __future__ import annotations

from governed_ai.adapters.common.guard import (
    GATE_COMMANDS,
    MEDIATED_SIGNAL_COMMANDS,
    PRODUCT_WRITE_COMMANDS,
    CapabilityNotEnforceableError,
    ExecutionGuardError,
    UnsupportedContractError,
    validate_requested_commands,
)

__all__ = [
    "CapabilityNotEnforceableError",
    "ExecutionGuardError",
    "GATE_COMMANDS",
    "MEDIATED_SIGNAL_COMMANDS",
    "PRODUCT_WRITE_COMMANDS",
    "UnsupportedContractError",
    "validate_requested_commands",
]
