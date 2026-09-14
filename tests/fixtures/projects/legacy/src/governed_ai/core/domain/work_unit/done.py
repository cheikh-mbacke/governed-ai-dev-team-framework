"""Definition-of-Done prerequisites for Work Units."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from governed_ai.core.workspace import Workspace


def missing_done_prerequisites(
    document: dict[str, Any],
    *,
    workspace: Workspace | None = None,
    expected_commit_sha: str | None = None,
) -> list[str]:
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

    if workspace is not None:
        binding = document.get("design_binding") or {}
        mode = str(binding.get("design_mode") or binding.get("mode") or "")
        if mode in {"conform", "adapt"}:
            from governed_ai.core.design_authority.gate_checks import (
                verify_visual_conformance_for_work_unit,
            )

            result = verify_visual_conformance_for_work_unit(
                workspace,
                document,
                expected_commit_sha=expected_commit_sha,
            )
            if not result.get("ok"):
                missing.append("valid visual conformance report")

    return missing
