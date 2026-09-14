"""Single effective execution scope computation."""

from __future__ import annotations

from typing import Any

from governed_ai.core.domain.run.path_policy import (
    CONTROL_PLANE_ONLY_PATH_PREFIXES,
    normalize_repo_path,
    sanitize_allowed_paths,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError
from governed_ai.core.orchestrator.boundary import path_is_allowed, path_scope_patterns

# Sentinel distinguishing "axis not applicable" from "axis present but empty".
_ABSENT = object()


def _pattern_subseteq(inner: str, outer: str) -> bool:
    """Return True when every path matching ``inner`` also matches ``outer``."""
    if inner == outer:
        return True
    probe = inner.rstrip("*").rstrip("/")
    if not probe:
        return path_is_allowed(".", [outer]) or path_is_allowed("./x", [outer])
    return path_is_allowed(probe, [outer]) or path_is_allowed(f"{probe}/x", [outer])


def _intersect_patterns(left: list[str], right: list[str]) -> list[str]:
    """Intersect two constrained glob/path lists conservatively.

    Keeps only the more restrictive pattern of each overlapping pair.
    Example: ``src/**`` ∩ ``src/restricted/**`` → ``[src/restricted/**]``.
    Empty ∩ anything → empty (both axes are present constraints).
    """
    if not left or not right:
        return []
    result: list[str] = []
    for left_pattern in left:
        for right_pattern in right:
            chosen: str | None = None
            if _pattern_subseteq(left_pattern, right_pattern):
                chosen = left_pattern
            elif _pattern_subseteq(right_pattern, left_pattern):
                chosen = right_pattern
            if chosen is not None and chosen not in result:
                result.append(chosen)
    return result


def _strip_control_plane(patterns: list[str]) -> list[str]:
    return sanitize_allowed_paths(patterns)


def _clean_patterns(patterns: list[str] | tuple[str, ...] | None) -> list[str]:
    return [
        normalize_repo_path(item)
        for item in (patterns or [])
        if str(item).strip()
    ]


def compute_effective_scope(
    *,
    work_unit: dict[str, Any],
    grant_allowed_paths: list[str] | tuple[str, ...] | None = None,
    role_write_paths: list[str] | tuple[str, ...] | None | object = _ABSENT,
    adapter_paths: list[str] | tuple[str, ...] | None | object = _ABSENT,
    execution_ceiling_paths: list[str] | tuple[str, ...] | None | object = _ABSENT,
    grant_axis_present: bool = True,
) -> dict[str, Any]:
    """Compute and materialize the unique effective scope.

    effective_scope =
        WU.scope.include
        ∩ Grant.allowed_paths
        ∩ Role.capabilities
        ∩ Adapter.capabilities
        ∩ ExecutionCeiling
        − WU.scope.exclude
        − ControlPlaneOnlyPaths

    Axis semantics:
    - absent / not applicable (``None`` for optional axes, or ``grant_axis_present=False``):
      skip the axis (do not constrain);
    - present but empty (``[]``): forbids all writes (intersection yields empty).
    """
    scope = work_unit.get("scope") or {}
    include = path_scope_patterns(scope.get("include") or [])
    exclude = path_scope_patterns(scope.get("exclude") or [])

    def _axis(
        label: str,
        value: list[str] | tuple[str, ...] | None | object,
        *,
        present: bool,
        strip_cp: bool = False,
    ) -> tuple[str, list[str] | None]:
        if not present or value is _ABSENT:
            return label, None
        if value is None:
            return label, None
        cleaned = _clean_patterns(list(value))  # type: ignore[arg-type]
        if strip_cp:
            cleaned = _strip_control_plane(cleaned)
        return label, cleaned

    # Work Unit include: empty after path filtering means unconstrained (same
    # semantics as boundary.classify — no path patterns to enforce). An explicit
    # non-empty include is a present axis.
    wu_include_axis: list[str] | None = include if include else None

    axes_raw: list[tuple[str, list[str] | None]] = [
        ("work_unit.scope.include", wu_include_axis),
        _axis(
            "grant.allowed_paths",
            grant_allowed_paths,
            present=grant_axis_present,
            strip_cp=True,
        ),
        _axis("role.capabilities", role_write_paths, present=role_write_paths is not _ABSENT),
        _axis("adapter.capabilities", adapter_paths, present=adapter_paths is not _ABSENT),
        _axis(
            "execution_ceiling",
            execution_ceiling_paths,
            present=execution_ceiling_paths is not _ABSENT,
        ),
    ]

    effective: list[str] = []
    constrained = False
    axis_snapshot: dict[str, list[str] | None] = {}
    for label, patterns in axes_raw:
        axis_snapshot[label] = None if patterns is None else list(patterns)
        if patterns is None:
            continue
        if not constrained:
            effective = list(patterns)
            constrained = True
        else:
            effective = _intersect_patterns(effective, patterns)

    effective = _strip_control_plane(effective)

    if exclude:
        effective = [
            pattern
            for pattern in effective
            if not path_is_allowed(pattern.rstrip("*"), exclude)
        ]

    contradictions: list[str] = []
    for path in include:
        if any(
            normalize_repo_path(path).startswith(prefix)
            for prefix in CONTROL_PLANE_ONLY_PATH_PREFIXES
        ):
            contradictions.append(path)

    if contradictions:
        raise ExecutionGatewayError(
            StructuredError(
                code="forbidden_control_plane_path",
                message="scope include overlaps Control-Plane-only paths",
                path="effective_scope",
                details={"paths": contradictions},
            )
        )

    grant = (
        _strip_control_plane(list(grant_allowed_paths or []))
        if grant_axis_present and grant_allowed_paths is not None
        else None
    )
    if include and grant is not None and grant and not _intersect_patterns(include, grant):
        raise ExecutionGatewayError(
            StructuredError(
                code="contradictory_path_policy",
                message="Work Unit scope.include and grant.allowed_paths do not intersect",
                path="effective_scope",
                details={"include": include, "grant": grant},
            )
        )

    if constrained and not effective:
        raise ExecutionGatewayError(
            StructuredError(
                code="empty_effective_scope",
                message="effective execution scope is empty after intersecting constraints",
                path="effective_scope",
                details=axis_snapshot,
            )
        )

    return {
        "schema_version": 1,
        "include": effective,
        "exclude": exclude,
        "control_plane_blocked": list(CONTROL_PLANE_ONLY_PATH_PREFIXES),
        "axes": axis_snapshot,
    }
