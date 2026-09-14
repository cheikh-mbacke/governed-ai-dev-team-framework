"""Select the correct frontend procedure from design_mode."""

from __future__ import annotations

from typing import Any

from governed_ai.core.design_authority.models import (
    CREATIVE_PROCEDURES,
    MODE_TO_PROCEDURE,
)


class ProcedureSelectionError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def select_frontend_procedure(
    *,
    design_mode: str | None,
    requested_procedure: str | None = None,
    allow_frontend_design_alias: bool = True,
) -> str:
    """Return the procedure that must be used for implementation.

    ``frontend-design`` remains as a compatibility alias that resolves to
    ``create-frontend-design`` only for create/explore. Using it as the primary
    procedure under conform/adapt is refused.
    """
    mode = (design_mode or "create").lower()
    if requested_procedure == "frontend-design" and allow_frontend_design_alias:
        if mode in {"create", "explore"}:
            return "create-frontend-design"
        raise ProcedureSelectionError(
            "creative_procedure_forbidden_for_mode",
            "frontend-design (creative) must not be the primary procedure under "
            f"design_mode={mode!r}",
            details={"design_mode": mode, "requested_procedure": requested_procedure},
        )

    if requested_procedure in CREATIVE_PROCEDURES and mode in {"conform", "adapt", "maintain"}:
        raise ProcedureSelectionError(
            "creative_procedure_forbidden_for_mode",
            f"procedure {requested_procedure!r} is not allowed for design_mode={mode!r}",
            details={"design_mode": mode, "requested_procedure": requested_procedure},
        )

    if requested_procedure and requested_procedure not in CREATIVE_PROCEDURES:
        # Explicit non-creative request wins when compatible.
        expected = MODE_TO_PROCEDURE.get(mode)
        if expected and requested_procedure != expected and mode in {"conform", "adapt"}:
            raise ProcedureSelectionError(
                "procedure_mode_mismatch",
                f"procedure {requested_procedure!r} does not match design_mode={mode!r}",
                details={
                    "design_mode": mode,
                    "requested_procedure": requested_procedure,
                    "expected_procedure": expected,
                },
            )
        return requested_procedure

    return MODE_TO_PROCEDURE.get(mode, "create-frontend-design")


def assert_procedure_matches_binding(
    work_unit: dict[str, Any], procedure_id: str
) -> None:
    binding = work_unit.get("design_binding") or {}
    mode = binding.get("design_mode")
    if not mode:
        return
    select_frontend_procedure(design_mode=str(mode), requested_procedure=procedure_id)
