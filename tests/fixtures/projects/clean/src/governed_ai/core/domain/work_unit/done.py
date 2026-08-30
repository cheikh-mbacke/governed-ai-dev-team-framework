"""Definition-of-Done prerequisites for Work Units."""

from __future__ import annotations

from typing import Any


def missing_done_prerequisites(document: dict[str, Any]) -> list[str]:
    """Return English labels for missing prerequisites (wrapper translates)."""
    req = document.get("required_verification", {})
    missing: list[str] = []

    if not document.get("evidence"):
        missing.append("evidence")
    if req.get("review") and document.get("outcomes", {}).get("review_status") != "approved":
        missing.append("approved review")
    if req.get("audit") and document.get("outcomes", {}).get("audit_status") != "passed":
        missing.append("required audit")
    if req.get("human_acceptance") and document.get("outcomes", {}).get("human_acceptance") not in (
        "passed",
        "accepted",
    ):
        missing.append("human acceptance")
    critical = document.get("outcomes", {}).get("critical_open_items", [])
    if critical:
        missing.append("resolution/decision for critical open items")

    return missing
