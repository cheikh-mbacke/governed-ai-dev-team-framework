"""Aggregate consented Feedback Exports in learning/inbox into a summary index."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_ai.feedback.common import now_iso

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass(frozen=True, slots=True)
class AggregateResult:
    index_path: Path
    export_count: int
    observation_count: int


def _bump(counter: dict[str, int], key: str | None, amount: int = 1) -> None:
    label = key if key else "unknown"
    counter[label] = counter.get(label, 0) + amount


def _load_exports(inbox: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted(inbox.glob("EXP-*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(document, dict):
            documents.append(document)
    return documents


def build_aggregate(inbox: Path) -> dict[str, Any]:
    """Scan inbox JSON exports and build a cross-project learning index."""
    by_framework: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_recurrence: dict[str, int] = {}
    by_project_ref: dict[str, int] = {}
    actionable: list[dict[str, Any]] = []
    export_ids: list[str] = []
    observation_total = 0
    transmission_statuses: Counter[str] = Counter()

    documents = _load_exports(inbox)
    for document in documents:
        export_id = str(document.get("export_id") or "unknown")
        export_ids.append(export_id)
        framework_version = str(document.get("framework_version") or "unknown")
        project_ref = str(document.get("project_ref") or "unknown")
        _bump(by_framework, framework_version)
        _bump(by_project_ref, project_ref)

        rows = [row for row in (document.get("observations") or []) if isinstance(row, dict)]
        if rows:
            for row in rows:
                observation_total += 1
                category = row.get("category")
                origin = (row.get("classification") or {}).get("origin") or row.get("origin")
                severity = row.get("severity")
                recurrence = row.get("recurrence_key") or row.get("recurrence_ref")
                _bump(by_category, str(category) if category else None)
                _bump(by_origin, str(origin) if origin else None)
                _bump(by_severity, str(severity) if severity else None)
                if recurrence:
                    _bump(by_recurrence, str(recurrence))
                if origin == "framework" or severity in {"high", "critical"}:
                    actionable.append(
                        {
                            "export_id": export_id,
                            "project_ref": project_ref,
                            "framework_version": framework_version,
                            "observation_id": row.get("id") or row.get("observation_ref"),
                            "category": category,
                            "origin": origin,
                            "severity": severity,
                            "recurrence_key": recurrence,
                            "symptom": row.get("symptom"),
                            "candidate_improvement": row.get("candidate_improvement"),
                            "occurrence_count": row.get("occurrence_count") or 1,
                        }
                    )
        else:
            # Aggregate/structured exports: use summary buckets only.
            summary = document.get("summary") or {}
            if isinstance(summary, dict):
                observation_total += int(summary.get("total") or 0)
                for key, bucket in (
                    ("by_category", by_category),
                    ("by_origin", by_origin),
                    ("by_severity", by_severity),
                ):
                    values = summary.get(key) or {}
                    if isinstance(values, dict):
                        for name, count in values.items():
                            if isinstance(count, int):
                                _bump(bucket, str(name), count)

        transmission = document.get("transmission") or {}
        if isinstance(transmission, dict) and transmission.get("status"):
            transmission_statuses[str(transmission["status"])] += 1

    actionable.sort(
        key=lambda item: (
            -SEVERITY_RANK.get(str(item.get("severity") or ""), 0),
            -int(item.get("occurrence_count") or 1),
            str(item.get("recurrence_key") or ""),
        )
    )

    return {
        "generated_at": now_iso(),
        "export_count": len(export_ids),
        "observation_count": observation_total,
        "export_ids": export_ids,
        "by_framework_version": dict(sorted(by_framework.items())),
        "by_project_ref": dict(sorted(by_project_ref.items())),
        "by_category": dict(sorted(by_category.items())),
        "by_origin": dict(sorted(by_origin.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "by_recurrence_key": dict(
            sorted(by_recurrence.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "transmission_status_counts": dict(sorted(transmission_statuses.items())),
        "actionable_for_framework": actionable[:100],
    }


def write_aggregate(
    *,
    inbox: Path,
    output: Path | None = None,
) -> AggregateResult:
    inbox.mkdir(parents=True, exist_ok=True)
    index = build_aggregate(inbox)
    target = output or (inbox.parent / "aggregate" / "latest.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return AggregateResult(
        index_path=target,
        export_count=int(index["export_count"]),
        observation_count=int(index["observation_count"]),
    )
