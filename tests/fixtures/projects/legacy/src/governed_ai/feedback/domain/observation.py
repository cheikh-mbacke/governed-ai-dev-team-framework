"""Observation identity, recurrence coalesce, and status vocabulary."""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from pathlib import Path
from typing import Any

UNRESOLVED_STATUSES = frozenset({"open", "acknowledged", "candidate_change"})
TERMINAL_STATUSES = frozenset({"resolved", "rejected"})
ALL_STATUSES = UNRESOLVED_STATUSES | TERMINAL_STATUSES

VALID_ORIGINS = frozenset(
    {
        "framework",
        "project",
        "environment",
        "external_service",
        "human_process",
        "unknown",
    }
)
VALID_CONFIDENCES = frozenset({"low", "probable", "high", "confirmed"})

# Forward-only Observation lifecycle (Document 10 / Document 12 TransitionObservation).
NORMATIVE_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"acknowledged", "candidate_change", "resolved", "rejected"}),
    "acknowledged": frozenset({"candidate_change", "resolved", "rejected"}),
    "candidate_change": frozenset({"resolved", "rejected"}),
    "resolved": frozenset(),
    "rejected": frozenset(),
}

SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def normalize_recurrence_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def occurrence_count_of(document: dict[str, Any]) -> int:
    raw = document.get("occurrence_count")
    if isinstance(raw, int) and raw >= 1:
        return raw
    return 1


def revision_of(document: dict[str, Any]) -> int:
    raw = document.get("revision")
    if isinstance(raw, int) and raw >= 1:
        return raw
    return 1


def is_transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in NORMATIVE_TRANSITIONS.get(from_status, frozenset())


def iter_permitted_transitions() -> list[tuple[str, str]]:
    return sorted(
        (from_status, to_status)
        for from_status, targets in NORMATIVE_TRANSITIONS.items()
        for to_status in targets
    )


def iter_forbidden_transitions() -> list[tuple[str, str]]:
    forbidden: list[tuple[str, str]] = []
    for from_status, to_status in product(ALL_STATUSES, ALL_STATUSES):
        if from_status == to_status:
            continue
        if not is_transition_allowed(from_status, to_status):
            forbidden.append((from_status, to_status))
    return sorted(forbidden)


def find_coalesce_candidate(
    observations: list[tuple[Path, dict[str, Any]]],
    *,
    recurrence_key: str | None,
    work_unit: str | None,
) -> tuple[Path, dict[str, Any]] | None:
    """Return the oldest unresolved observation sharing key + Work Unit."""
    key = normalize_recurrence_key(recurrence_key)
    if key is None:
        return None
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path, payload in observations:
        if normalize_recurrence_key(payload.get("recurrence_key")) != key:
            continue
        if payload.get("work_unit") != work_unit:
            continue
        if payload.get("status") not in UNRESOLVED_STATUSES:
            continue
        matches.append((path, payload))
    if not matches:
        return None
    matches.sort(key=lambda item: (str(item[1].get("recorded_at") or ""), item[0].name))
    return matches[0]


def apply_coalesce(
    existing: dict[str, Any],
    *,
    now: str,
    blocked_minutes: int,
    rework_required: bool,
    human_intervention: bool,
    affected_work_units: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    severity: str,
    workaround: str | None,
    candidate_improvement: str | None,
) -> dict[str, Any]:
    """Fold a new sighting into an existing unresolved Observation.

    The first symptom, classification, status and identity stay. Count,
    last_recorded_at, evidence, impact flags and severity may rise.
    """
    updated = deepcopy(existing)
    impact = dict(updated.get("impact") or {})
    previous_minutes = int(impact.get("blocked_minutes") or 0)
    impact["blocked_minutes"] = previous_minutes + max(0, int(blocked_minutes))
    impact["rework_required"] = bool(impact.get("rework_required")) or bool(rework_required)
    impact["human_intervention"] = bool(impact.get("human_intervention")) or bool(
        human_intervention
    )
    affected = set(impact.get("affected_work_units") or [])
    affected.update(affected_work_units)
    impact["affected_work_units"] = sorted(affected)
    updated["impact"] = impact

    evidence = set(updated.get("evidence_refs") or [])
    evidence.update(evidence_refs)
    updated["evidence_refs"] = sorted(evidence)

    current_rank = SEVERITY_RANK.get(str(updated.get("severity") or "medium"), 2)
    incoming_rank = SEVERITY_RANK.get(severity, current_rank)
    if incoming_rank > current_rank:
        updated["severity"] = severity

    if workaround and not updated.get("workaround"):
        updated["workaround"] = workaround
    if candidate_improvement and not updated.get("candidate_improvement"):
        updated["candidate_improvement"] = candidate_improvement

    updated["occurrence_count"] = occurrence_count_of(updated) + 1
    updated["last_recorded_at"] = now
    updated["revision"] = revision_of(updated) + 1
    return updated


def apply_transition(
    existing: dict[str, Any],
    *,
    to_status: str,
    resolution: str | None = None,
    origin: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    """Apply a permitted status transition (and optional classification update)."""
    current_status = str(existing.get("status") or "")
    if not is_transition_allowed(current_status, to_status):
        raise ValueError(f"transition {current_status!r} -> {to_status!r} not allowed")
    if to_status in TERMINAL_STATUSES:
        text = (resolution or "").strip()
        if not text:
            raise ValueError("resolution is required when resolving or rejecting")
    if (origin is None) ^ (confidence is None):
        raise ValueError("classification origin and confidence must be provided together")
    if origin is not None and origin not in VALID_ORIGINS:
        raise ValueError(f"unsupported origin {origin!r}")
    if confidence is not None and confidence not in VALID_CONFIDENCES:
        raise ValueError(f"unsupported confidence {confidence!r}")

    updated = deepcopy(existing)
    updated["status"] = to_status
    if to_status in TERMINAL_STATUSES:
        updated["resolution"] = (resolution or "").strip()
    if origin is not None and confidence is not None:
        updated["classification"] = {"origin": origin, "confidence": confidence}
    updated["revision"] = revision_of(updated) + 1
    return updated
