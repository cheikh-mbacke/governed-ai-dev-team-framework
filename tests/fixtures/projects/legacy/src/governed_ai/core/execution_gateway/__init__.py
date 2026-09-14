"""Agent Execution Gateway — contractual boundary between Core and external agents.

The Core never consumes provider-specific IDE conventions directly. Adapters
speak the gateway contract; a clearly isolated legacy adapter may translate
older prose+JSON handoffs into the canonical shape.

Authoritative mutations still go through ``CommandGateway``.
"""

from __future__ import annotations

from governed_ai.core.execution_gateway.capabilities import (
    CapabilityDescriptor,
    assert_capabilities,
)
from governed_ai.core.execution_gateway.check_registry import (
    CheckDefinition,
    normalize_check_name,
    resolve_required_checks,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.execution_gateway.gateway import AgentExecutionGateway, GatewayOutcome
from governed_ai.core.execution_gateway.progress import ProgressEventType, is_useful_progress

__all__ = [
    "AgentExecutionGateway",
    "CapabilityDescriptor",
    "CheckDefinition",
    "ExecutionGatewayError",
    "GatewayOutcome",
    "ProgressEventType",
    "StructuredError",
    "assert_capabilities",
    "is_useful_progress",
    "normalize_check_name",
    "resolve_required_checks",
]
