"""Divergence classification for visual conformance."""

from __future__ import annotations

from typing import Any

from governed_ai.core.design_authority.models import (
    DivergenceKind,
    DivergenceSeverity,
)

BLOCKING_KINDS_FOR_AUTHORITATIVE: frozenset[str] = frozenset(
    {
        "defect",
        "design_system_conflict",
        "product_decision_required",
        "reference_outdated",
    }
)


def classify_divergence(
    *,
    kind: DivergenceKind | str,
    severity: DivergenceSeverity | str,
    authority_level: str,
    explanation: str,
    contract_tolerance_rule: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured divergence record.

    Advisory references never auto-block. Allowed adaptations require an
    explicit Design Contract tolerance rule.
    """
    kind_s = str(kind)
    severity_s = str(severity)
    if kind_s == "allowed_adaptation" and not contract_tolerance_rule:
        raise ValueError(
            "allowed_adaptation divergences require a Design Contract tolerance rule"
        )

    blocks = False
    if authority_level == "authoritative":
        if severity_s == "blocking" or (
            kind_s in BLOCKING_KINDS_FOR_AUTHORITATIVE and severity_s in {"blocking", "major"}
        ):
            blocks = severity_s == "blocking"
    elif authority_level == "advisory":
        blocks = False
        if severity_s == "blocking":
            severity_s = "advisory"

    return {
        "kind": kind_s,
        "severity": severity_s,
        "authority_level": authority_level,
        "blocks_progress": blocks,
        "explanation": explanation,
        "contract_tolerance_rule": contract_tolerance_rule,
        "details": details or {},
    }


def report_blocks_progress(divergences: list[dict[str, Any]]) -> bool:
    return any(bool(item.get("blocks_progress")) for item in divergences)
