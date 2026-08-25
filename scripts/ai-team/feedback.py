#!/usr/bin/env python3
"""Record, summarize, and export structured framework-learning feedback."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

try:
    from feedback_common import (
        AI,
        ROOT,
        atomic_write_json,
        atomic_write_yaml,
        find_work_unit,
        generated_id,
        load_yaml_directory,
        metadata,
        now_iso,
        observation_summary,
        relates_to_work_unit,
        validate_payload,
    )
except ModuleNotFoundError:
    print("Missing dependency: PyYAML and/or jsonschema. Install requirements first.")
    raise SystemExit(1)


CATEGORIES = [
    "readiness",
    "decomposition",
    "context",
    "staffing",
    "permissions",
    "orchestration",
    "tooling",
    "testing",
    "review",
    "audit",
    "human_gate",
    "environment",
    "documentation",
    "other",
]
SEVERITIES = ["info", "low", "medium", "high", "critical"]
ORIGINS = [
    "framework",
    "project",
    "environment",
    "external_service",
    "human_process",
    "unknown",
]
CONFIDENCES = ["low", "probable", "high", "confirmed"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Structured learning loop for the governed AI team framework"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="record one observed friction")
    record.add_argument("--category", choices=CATEGORIES, required=True)
    record.add_argument("--severity", choices=SEVERITIES, default="medium")
    record.add_argument("--origin", choices=ORIGINS, default="unknown")
    record.add_argument("--confidence", choices=CONFIDENCES, default="low")
    record.add_argument("--symptom", required=True)
    record.add_argument("--work-unit")
    record.add_argument("--phase")
    record.add_argument("--recorded-by")
    record.add_argument("--blocked-minutes", type=int, default=0)
    record.add_argument("--rework-required", action="store_true")
    record.add_argument("--human-intervention", action="store_true")
    record.add_argument("--affected-work-unit", action="append", default=[])
    record.add_argument("--evidence-ref", action="append", default=[])
    record.add_argument("--workaround")
    record.add_argument("--candidate-improvement")
    record.add_argument("--recurrence-key")
    record.add_argument(
        "--status",
        choices=["open", "acknowledged", "candidate_change", "resolved", "rejected"],
        default="open",
    )
    record.add_argument("--resolution")

    retrospective = subparsers.add_parser(
        "retrospective", help="generate a deterministic Work Unit or project snapshot"
    )
    scope = retrospective.add_mutually_exclusive_group(required=True)
    scope.add_argument("--work-unit")
    scope.add_argument("--project", action="store_true")
    retrospective.add_argument("--notes")
    retrospective.add_argument("--output")

    export = subparsers.add_parser(
        "export", help="export feedback for cross-project analysis"
    )
    export.add_argument(
        "--detail-level",
        choices=["aggregate", "structured", "full"],
        default="structured",
    )
    export.add_argument("--include-project-id", action="store_true")
    export.add_argument("--output")
    return parser


def record_observation(args: argparse.Namespace) -> int:
    if args.blocked_minutes < 0:
        raise ValueError("--blocked-minutes cannot be negative")
    if args.work_unit and find_work_unit(args.work_unit) is None:
        raise ValueError(f"Work Unit not found: {args.work_unit}")
    for work_unit in args.affected_work_unit:
        if find_work_unit(work_unit) is None:
            raise ValueError(f"Affected Work Unit not found: {work_unit}")

    meta = metadata()
    observation_id = generated_id("OBS")
    payload = {
        "id": observation_id,
        "recorded_at": now_iso(),
        "recorded_by": args.recorded_by,
        "project_id": meta["project_id"],
        "framework_version": meta["framework_version"],
        "constitution_version": meta["constitution_version"],
        "work_unit": args.work_unit,
        "phase": args.phase or meta["phase"],
        "category": args.category,
        "severity": args.severity,
        "symptom": args.symptom,
        "classification": {
            "origin": args.origin,
            "confidence": args.confidence,
        },
        "impact": {
            "blocked_minutes": args.blocked_minutes,
            "rework_required": args.rework_required,
            "human_intervention": args.human_intervention,
            "affected_work_units": sorted(set(args.affected_work_unit)),
        },
        "evidence_refs": sorted(set(args.evidence_ref)),
        "workaround": args.workaround,
        "candidate_improvement": args.candidate_improvement,
        "recurrence_key": args.recurrence_key,
        "status": args.status,
        "resolution": args.resolution,
    }
    validate_payload(payload, "observation.schema.json")
    path = AI / "observations" / f"{observation_id}.yaml"
    atomic_write_yaml(path, payload)
    print(f"Recorded {observation_id}: {path.relative_to(ROOT)}")
    return 0


def _scoped_objects(directory: str, work_unit_id: str | None) -> list[dict]:
    return [
        payload
        for _path, payload in load_yaml_directory(AI / directory)
        if relates_to_work_unit(payload, work_unit_id)
    ]


def generate_retrospective(args: argparse.Namespace) -> int:
    meta = metadata()
    work_unit_id = args.work_unit
    work_units = []
    if work_unit_id:
        found = find_work_unit(work_unit_id)
        if found is None:
            raise ValueError(f"Work Unit not found: {work_unit_id}")
        work_units = [found[1]]
        scope_type = "work_unit"
        scope_ref = work_unit_id
    else:
        work_units = [data for _path, data in load_yaml_directory(AI / "work-units")]
        scope_type = "project"
        scope_ref = meta["project_id"]

    observations = _scoped_objects("observations", work_unit_id)
    events = _scoped_objects("events", work_unit_id)
    decisions = _scoped_objects("decisions", work_unit_id)
    findings = _scoped_objects("findings", work_unit_id)
    acceptances = _scoped_objects("acceptance", work_unit_id)
    summary, signals = observation_summary(observations)
    signals["event_types"] = dict(
        sorted(Counter(item.get("type", "unknown") for item in events).items())
    )
    signals["work_unit_statuses"] = dict(
        sorted(Counter(item.get("status", "unknown") for item in work_units).items())
    )
    unresolved = {"open", "acknowledged", "candidate_change"}

    retrospective_id = generated_id("RET")
    payload = {
        "id": retrospective_id,
        "generated_at": now_iso(),
        "project_id": meta["project_id"],
        "framework_version": meta["framework_version"],
        "constitution_version": meta["constitution_version"],
        "scope": {"type": scope_type, "ref": scope_ref},
        "source_snapshot": {
            "observations": len(observations),
            "events": len(events),
            "decisions": len(decisions),
            "findings": len(findings),
            "acceptances": len(acceptances),
            "work_units": len(work_units),
        },
        "observation_summary": summary,
        "signals": signals,
        "observation_refs": [item["id"] for item in observations],
        "unresolved_observation_refs": [
            item["id"] for item in observations if item.get("status") in unresolved
        ],
        "notes": args.notes,
        "status": "generated",
    }
    validate_payload(payload, "retrospective.schema.json")
    path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else AI / "retrospectives" / f"{retrospective_id}.yaml"
    )
    atomic_write_yaml(path, payload)
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f"Generated {retrospective_id}: {shown}")
    return 0


def _hash_ref(value: str | None) -> str:
    return hashlib.sha256((value or "unknown").encode("utf-8")).hexdigest()[:12]


def _structured_observation(item: dict) -> dict:
    recurrence = item.get("recurrence_key")
    return {
        "id": item.get("id"),
        "category": item.get("category"),
        "severity": item.get("severity"),
        "origin": (item.get("classification") or {}).get("origin"),
        "confidence": (item.get("classification") or {}).get("confidence"),
        "impact": item.get("impact") or {},
        "recurrence_ref": _hash_ref(recurrence) if recurrence else None,
        "status": item.get("status"),
    }


def _full_without_project_id(item: dict, project_ref: str, include_id: bool) -> dict:
    result = deepcopy(item)
    if not include_id:
        result.pop("project_id", None)
        result["project_ref"] = project_ref
        if (result.get("scope") or {}).get("type") == "project":
            result["scope"]["ref"] = project_ref
    return result


def export_feedback(args: argparse.Namespace) -> int:
    meta = metadata()
    observations = [data for _path, data in load_yaml_directory(AI / "observations")]
    retrospectives = [
        data for _path, data in load_yaml_directory(AI / "retrospectives")
    ]
    summary, signals = observation_summary(observations)
    summary["signals"] = signals
    summary["retrospectives"] = len(retrospectives)
    project_ref = _hash_ref(meta["project_id"])

    if args.detail_level == "aggregate":
        exported_observations = []
        exported_retrospectives = []
    elif args.detail_level == "structured":
        exported_observations = [_structured_observation(item) for item in observations]
        exported_retrospectives = [
            {
                "id": item.get("id"),
                "scope_type": (item.get("scope") or {}).get("type"),
                "observation_summary": item.get("observation_summary") or {},
                "signals": item.get("signals") or {},
                "status": item.get("status"),
            }
            for item in retrospectives
        ]
    else:
        exported_observations = [
            _full_without_project_id(item, project_ref, args.include_project_id)
            for item in observations
        ]
        exported_retrospectives = [
            _full_without_project_id(item, project_ref, args.include_project_id)
            for item in retrospectives
        ]

    payload = {
        "format_version": "1.0",
        "generated_at": now_iso(),
        "detail_level": args.detail_level,
        "project_ref": project_ref,
        "framework_version": meta["framework_version"],
        "constitution_version": meta["constitution_version"],
        "summary": summary,
        "observations": exported_observations,
        "retrospectives": exported_retrospectives,
    }
    if args.include_project_id:
        payload["project_id"] = meta["project_id"]
    validate_payload(payload, "feedback-export.schema.json")
    timestamp = now_iso().replace(":", "").replace("+00:00", "Z")
    path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else AI / "metrics" / f"framework-feedback-{timestamp}.json"
    )
    atomic_write_json(path, payload)
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f"Exported {args.detail_level} feedback: {shown}")
    if args.detail_level == "full":
        print("WARNING: full exports may contain project-sensitive free text and references.")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "record":
            return record_observation(args)
        if args.command == "retrospective":
            return generate_retrospective(args)
        return export_feedback(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
