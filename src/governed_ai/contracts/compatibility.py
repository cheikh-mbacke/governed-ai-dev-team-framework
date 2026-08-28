"""Compatibility negotiation helpers between core and adapters (Phase 2+)."""

from __future__ import annotations

from typing import TypedDict


class CompatibilityIssue(TypedDict, total=False):
    """Single incompatibility or fallback note (Document 12 §4)."""

    code: str
    path: str
    required: str
    available: str
    fallback: str


class CompatibilityReport(TypedDict):
    """Result of adapter compatibility check (Document 12 §4)."""

    compatible: bool
    adapter_id: str
    role_id: str
    procedure_id: str
    issues: list[CompatibilityIssue]
