"""Morning report aggregation (Document 6 §13).

A single end-of-session report, not scattered real-time notifications
(critical security alerts excepted, §9.5 — those are already sent
immediately as BLOCKER events, not deferred here). This module only
summarizes already-persisted records; it never mutates anything and never
judges — every grouping rule below is a plain structural filter.
"""

from __future__ import annotations

from typing import Any

# `human_test` is the successful unattended terminal point: implementation,
# verification, review, audit and (where required) integration succeeded, but
# final human acceptance intentionally remains pending.
DONE_STATUSES = frozenset({"human_test", "done"})
PAUSED_STATUSES = frozenset({"waiting_decision", "blocked"})
CANCELLED_STATUSES = frozenset({"cancelled"})


def _attempts_for_work_unit(attempts: list[dict[str, Any]], work_unit_id: str) -> list[dict[str, Any]]:
    return [a for a in attempts if a.get("work_unit_id") == work_unit_id]


def build_morning_report(
    *,
    run_document: dict[str, Any],
    work_unit_documents: dict[str, dict[str, Any] | None],
    attempts: list[dict[str, Any]],
    leases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    escalations: list[dict[str, Any]],
    events: list[dict[str, Any]],
    integration_merges: list[dict[str, Any]] | None = None,
    release_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    completed_work_units = []
    paused_work_units = []
    cancelled_work_units = []
    unknown_work_units = []

    for work_unit_id in run_document.get("work_unit_ids") or []:
        wu_document = work_unit_documents.get(work_unit_id)
        if wu_document is None:
            unknown_work_units.append(work_unit_id)
            continue
        status = wu_document.get("status")
        wu_attempts = _attempts_for_work_unit(attempts, work_unit_id)
        if status in DONE_STATUSES:
            completed_work_units.append(
                {
                    "work_unit_id": work_unit_id,
                    "status": status,
                    "successful_attempts": [
                        a["id"] for a in wu_attempts if a.get("status") == "succeeded"
                    ],
                }
            )
        elif status in PAUSED_STATUSES:
            pending = [
                {
                    "decision_id": d["id"],
                    "trigger": d.get("trigger"),
                    "proposed_entry_id": d.get("proposed_entry_id"),
                    "rejection_reason": d.get("rejection_reason"),
                }
                for d in decisions
                if d.get("work_unit_id") == work_unit_id and not d.get("resolved")
            ]
            paused_work_units.append(
                {"work_unit_id": work_unit_id, "status": status, "pending_decisions": pending}
            )
        elif status in CANCELLED_STATUSES:
            cancelled_work_units.append(
                {
                    "work_unit_id": work_unit_id,
                    "status": status,
                    "reason": (wu_document.get("outcomes") or {}).get("review_status"),
                }
            )

    automatic_decision_resolutions = [
        {
            "decision_id": d["id"],
            "work_unit_id": d.get("work_unit_id"),
            "proposed_entry_id": d.get("proposed_entry_id"),
            "resolved_at": d.get("resolved_at"),
        }
        for d in decisions
        if d.get("resolved")
    ]

    risk_escalations = [
        {
            "work_unit_id": e.get("work_unit_id"),
            "dimension": e.get("dimension"),
            "previous_state": e.get("previous_state"),
            "new_state": e.get("new_state"),
            "reason": e.get("reason"),
            "escalated_at": e.get("escalated_at"),
        }
        for e in escalations
    ]

    fencing_reassignments = [
        {
            "work_unit_id": lease.get("work_unit_id"),
            "superseded_lease_id": lease.get("id"),
            "superseded_by": lease.get("superseded_by"),
        }
        for lease in leases
        if lease.get("status") == "superseded"
    ]

    blocker_events = [
        {
            "event_id": event.get("id"),
            "work_unit": event.get("work_unit"),
            "summary": event.get("summary"),
            "details": event.get("details"),
        }
        for event in events
        if event.get("type") == "BLOCKER"
    ]

    return {
        "run_id": run_document.get("id"),
        "status": run_document.get("status"),
        "stop_condition": run_document.get("stop_condition"),
        "completed_work_units": completed_work_units,
        "paused_work_units": paused_work_units,
        "cancelled_work_units": cancelled_work_units,
        "unknown_work_units": unknown_work_units,
        "automatic_decision_resolutions": automatic_decision_resolutions,
        "risk_escalations": risk_escalations,
        "anomalies": {
            "fencing_reassignments": fencing_reassignments,
            "blocker_events": blocker_events,
        },
        "integration_merges": integration_merges or [],
        "release_candidates": release_candidates or [],
    }
