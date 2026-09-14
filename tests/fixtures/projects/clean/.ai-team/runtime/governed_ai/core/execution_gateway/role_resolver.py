"""Central role resolution — never silently swap frontend for backend."""

from __future__ import annotations

from typing import Any

from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError

IMPLEMENTATION_ROLES = frozenset({"backend-developer", "frontend-developer"})

KNOWN_ROLES = frozenset(
    {
        "backend-developer",
        "frontend-developer",
        "qa-test",
        "code-reviewer",
        "security-reviewer",
        "auditor",
        "integration-steward",
        "control-plane",
        "architect",
        "product-designer",
        "design-system-steward",
        "visual-qa",
    }
)


def _role_candidates(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [candidate for item in value for candidate in _role_candidates(item)]
    if isinstance(value, dict):
        preferred_keys = (
            "role",
            "role_id",
            "primary_role",
            "implementer",
            "assigned_role",
        )
        preferred = [
            candidate
            for key in preferred_keys
            if key in value
            for candidate in _role_candidates(value[key])
        ]
        remaining = [
            candidate
            for key, item in value.items()
            if key not in preferred_keys
            for candidate in _role_candidates(item)
        ]
        return preferred + remaining
    return []


def resolve_role(
    *,
    work_unit: dict[str, Any],
    context_role: str | None = None,
    fallback_role: str | None = None,
    allowed_roles: frozenset[str] | set[str] | None = None,
) -> str:
    """Resolve role with explicit priority; refuse silent frontend→backend swap.

    Priority:
    1. staffing proposal / staffing
    2. compiled context package role
    3. Work Unit zone/area
    4. explicit fallback from the contract (never invent opposite area)
    """
    allowed = allowed_roles or IMPLEMENTATION_ROLES

    for source in (work_unit.get("staffing_proposal"), work_unit.get("staffing")):
        for candidate in _role_candidates(source):
            if candidate in allowed:
                return candidate

    if context_role and context_role in allowed:
        return context_role

    area = str((work_unit.get("zone") or {}).get("area") or "").lower()
    if area in {"frontend", "mobile"}:
        if "frontend-developer" in allowed:
            return "frontend-developer"
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_role",
                message=(
                    f"Work Unit area={area!r} requires frontend-developer but "
                    f"allowed roles are {sorted(allowed)}"
                ),
                path="role_id",
            )
        )
    if area in {"backend", "api", "data"}:
        if "backend-developer" in allowed:
            return "backend-developer"
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_role",
                message=(
                    f"Work Unit area={area!r} requires backend-developer but "
                    f"allowed roles are {sorted(allowed)}"
                ),
                path="role_id",
            )
        )

    if fallback_role and fallback_role in allowed:
        # Fallback must not contradict an explicit area hint.
        if area in {"frontend", "mobile"} and fallback_role == "backend-developer":
            raise ExecutionGatewayError(
                StructuredError(
                    code="unsupported_role",
                    message="refusing silent frontend→backend role substitution",
                    path="role_id",
                    details={"area": area, "fallback_role": fallback_role},
                )
            )
        return fallback_role

    raise ExecutionGatewayError(
        StructuredError(
            code="unsupported_role",
            message="unable to resolve an authorized role for this Work Unit",
            path="role_id",
            details={"area": area, "allowed": sorted(allowed)},
        )
    )


def assert_role_procedure(
    *,
    role_id: str,
    procedure_id: str,
    known_roles: set[str] | frozenset[str] | None,
    role_procedures: dict[str, set[str]] | None = None,
    supported_combinations: set[tuple[str, str]] | frozenset[tuple[str, str]] | None = None,
) -> None:
    """Refuse unknown roles and role/procedure pairs that are not explicitly attached.

    ``known_roles`` and ``role_procedures`` must be compiled from the active
    bundle. They are not optional soft hints: a missing registry refuses launch.
    A separate list of roles and procedures is never treated as their Cartesian
    product — use ``role_procedures`` or ``supported_combinations``.
    """
    if known_roles is None:
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_role",
                message="known_roles was not compiled from the active bundle",
                path="role_id",
            )
        )
    if role_id not in known_roles:
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_role",
                message=f"role {role_id!r} is not in the active bundle",
                path="role_id",
            )
        )
    if role_procedures is None and supported_combinations is None:
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_procedure",
                message="role_procedures was not compiled from the active bundle",
                path="procedure_id",
            )
        )
    if supported_combinations is not None:
        if (role_id, procedure_id) not in supported_combinations:
            raise ExecutionGatewayError(
                StructuredError(
                    code="unsupported_procedure",
                    message=(
                        f"combination ({role_id!r}, {procedure_id!r}) is not an "
                        "explicitly supported role/procedure pair"
                    ),
                    path="procedure_id",
                )
            )
        return
    assert role_procedures is not None
    attached = role_procedures.get(role_id) or set()
    if procedure_id not in attached:
        raise ExecutionGatewayError(
            StructuredError(
                code="unsupported_procedure",
                message=(
                    f"procedure {procedure_id!r} is not attached to role {role_id!r}"
                ),
                path="procedure_id",
            )
        )
