"""Pre-execution guards for Cursor runtime harness (AD-006-010).

Re-exports the shared, tool-agnostic implementation — see
``governed_ai.adapters.common.guard``. Kept as a distinct module (rather than
inlined at call sites) so existing imports (``adapters.cursor.runtime.guard``)
continue to work unchanged.
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
