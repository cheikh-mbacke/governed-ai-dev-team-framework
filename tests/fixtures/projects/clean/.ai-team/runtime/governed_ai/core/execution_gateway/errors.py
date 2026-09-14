"""Structured errors for the Agent Execution Gateway."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class StructuredError:
    code: str
    message: str
    path: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


class ExecutionGatewayError(RuntimeError):
    """Raised when a gateway invariant fails before or after adapter execution."""

    def __init__(self, error: StructuredError) -> None:
        super().__init__(f"{error.code}: {error.message}")
        self.error = error

    @property
    def code(self) -> str:
        return self.error.code
