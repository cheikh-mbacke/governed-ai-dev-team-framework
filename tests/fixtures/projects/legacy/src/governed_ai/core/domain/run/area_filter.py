"""Area filter on RunAuthorizationGrant (Document 27).

`allowed_areas` optionally restricts which Work Units a grant / Run may
dispatch, by `zone.area`. Pure helpers — no I/O.
"""

from __future__ import annotations

from typing import Any

# WorkUnit.zone.area enum minus `unknown` (Document 27 §3.1 / §3.5).
FILTERABLE_AREAS = frozenset(
    {
        "frontend",
        "backend",
        "fullstack",
        "mobile",
        "infra",
        "data",
    }
)

AREA_FILTER_DEPENDENCY_POLICIES = frozenset(
    {
        "skip_blocked",
        "stop_on_cross_area_dependency",
    }
)

DEFAULT_AREA_FILTER_DEPENDENCY_POLICY = "skip_blocked"


def work_unit_area(work_unit: dict[str, Any] | None) -> str:
    if not work_unit:
        return "unknown"
    area = str((work_unit.get("zone") or {}).get("area") or "unknown").lower()
    return area or "unknown"


def grant_allowed_areas(grant: dict[str, Any]) -> list[str] | None:
    """Return normalized areas when a filter is active, else None."""
    raw = grant.get("allowed_areas")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    return [str(item).lower() for item in raw]


def area_filter_active(grant: dict[str, Any]) -> bool:
    return grant_allowed_areas(grant) is not None


def area_filter_dependency_policy(grant: dict[str, Any]) -> str:
    raw = grant.get("area_filter_dependency_policy")
    if raw is None:
        return DEFAULT_AREA_FILTER_DEPENDENCY_POLICY
    return str(raw)


def is_area_eligible(work_unit: dict[str, Any] | None, grant: dict[str, Any]) -> bool:
    """True when the grant imposes no area filter, or the WU's area is listed."""
    allowed = grant_allowed_areas(grant)
    if allowed is None:
        return True
    area = work_unit_area(work_unit)
    if area == "unknown" or area not in FILTERABLE_AREAS:
        return False
    return area in allowed


def area_ineligibility_reason(
    work_unit: dict[str, Any] | None, grant: dict[str, Any]
) -> str | None:
    """Machine reason when a WU is outside the grant area filter, else None."""
    if is_area_eligible(work_unit, grant):
        return None
    return "area_filter_mismatch"


def normalize_allowed_areas_payload(raw: Any) -> list[str] | None:
    """Validate payload.allowed_areas; return normalized list or None if absent.

    Raises ValueError with a stable message on invalid shapes / values.
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("allowed_areas must be an array when present")
    if len(raw) == 0:
        raise ValueError("allowed_areas must be non-empty when present")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        area = str(item).lower()
        if area == "unknown":
            raise ValueError("allowed_areas must not include unknown")
        if area not in FILTERABLE_AREAS:
            raise ValueError(f"unsupported area in allowed_areas: {area!r}")
        if area not in seen:
            seen.add(area)
            normalized.append(area)
    return normalized


def normalize_dependency_policy_payload(
    raw: Any, *, filter_active: bool
) -> str | None:
    """Return policy to persist, or None when no area filter is active."""
    if not filter_active:
        if raw is not None:
            raise ValueError(
                "area_filter_dependency_policy requires allowed_areas"
            )
        return None
    if raw is None:
        return DEFAULT_AREA_FILTER_DEPENDENCY_POLICY
    policy = str(raw)
    if policy not in AREA_FILTER_DEPENDENCY_POLICIES:
        raise ValueError(
            f"unsupported area_filter_dependency_policy: {policy!r}"
        )
    return policy


def dependency_ids(work_unit: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for dependency in work_unit.get("dependencies") or []:
        dependency_id = dependency if isinstance(dependency, str) else dependency.get("id")
        if dependency_id:
            ids.append(str(dependency_id))
    return ids


def blocked_solely_by_cross_area_dependency(
    work_unit: dict[str, Any],
    *,
    grant: dict[str, Any],
    work_unit_documents: dict[str, dict[str, Any] | None],
) -> bool:
    """True when every unsatisfied dependency is outside the area filter.

    Satisfied deps (human_test / done) are ignored. Missing dependency
    documents are treated as unsatisfied and as outside the filter.
    """
    if not area_filter_active(grant) or not is_area_eligible(work_unit, grant):
        return False
    unsatisfied_outside = False
    for dependency_id in dependency_ids(work_unit):
        dependency_document = work_unit_documents.get(dependency_id)
        if dependency_document is not None and dependency_document.get("status") in {
            "human_test",
            "done",
        }:
            continue
        # Unsatisfied dependency.
        if is_area_eligible(dependency_document, grant):
            # Blocked by an in-filter (or filter-absent) dependency — not sole
            # cross-area blockage.
            return False
        unsatisfied_outside = True
    return unsatisfied_outside
