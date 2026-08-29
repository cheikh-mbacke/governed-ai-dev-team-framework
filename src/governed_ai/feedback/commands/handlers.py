"""Feedback command handlers (record, retrospective, export)."""

from __future__ import annotations

import hashlib
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from governed_ai.core.workspace import Workspace
from governed_ai.feedback import common


@dataclass(frozen=True, slots=True)
class RecordObservationParams:
    category: str
    symptom: str
    severity: str = "medium"
    origin: str = "unknown"
    confidence: str = "low"
    work_unit: str | None = None
    phase: str | None = None
    recorded_by: str | None = None
    observation_id: str | None = None
    blocked_minutes: int = 0
    rework_required: bool = False
    human_intervention: bool = False
    affected_work_unit: tuple[str, ...] = ()
    evidence_ref: tuple[str, ...] = ()
    workaround: str | None = None
    candidate_improvement: str | None = None
    recurrence_key: str | None = None
    status: str = "open"
    resolution: str | None = None


@dataclass(frozen=True, slots=True)
class RecordObservationResult:
    observation_id: str
    path: Path
    display_path: Path


@dataclass(frozen=True, slots=True)
class RetrospectiveParams:
    work_unit: str | None = None
    project: bool = False
    notes: str | None = None
    output: str | None = None


@dataclass(frozen=True, slots=True)
class RetrospectiveResult:
    retrospective_id: str
    path: Path
    display_path: Path


@dataclass(frozen=True, slots=True)
class ExportParams:
    detail_level: str = "structured"
    include_project_id: bool = False
    output: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    display_path: Path
    detail_level: str
    show_full_warning: bool


def record_observation(
    workspace: Workspace, params: RecordObservationParams
) -> RecordObservationResult:
    payload = build_observation_document(workspace, params)
    path = workspace.ai_team / "observations" / f"{payload['id']}.yaml"
    common.atomic_write_yaml(path, payload)
    return RecordObservationResult(
        observation_id=payload["id"],
        path=path,
        display_path=path.relative_to(workspace.root),
    )


def build_observation_document(
    workspace: Workspace, params: RecordObservationParams
) -> dict:
    if params.blocked_minutes < 0:
        raise ValueError("--blocked-minutes cannot be negative")
    if params.work_unit and common.find_work_unit(workspace, params.work_unit) is None:
        raise ValueError(f"Work Unit not found: {params.work_unit}")
    for work_unit in params.affected_work_unit:
        if common.find_work_unit(workspace, work_unit) is None:
            raise ValueError(f"Affected Work Unit not found: {work_unit}")

    meta = common.metadata(workspace)
    observation_id = params.observation_id or common.generated_id("OBS")
    payload = {
        "id": observation_id,
        "recorded_at": common.now_iso(),
        "recorded_by": params.recorded_by,
        "project_id": meta["project_id"],
        "framework_version": meta["framework_version"],
        "constitution_version": meta["constitution_version"],
        "work_unit": params.work_unit,
        "phase": params.phase or meta["phase"],
        "category": params.category,
        "severity": params.severity,
        "symptom": params.symptom,
        "classification": {
            "origin": params.origin,
            "confidence": params.confidence,
        },
        "impact": {
            "blocked_minutes": params.blocked_minutes,
            "rework_required": params.rework_required,
            "human_intervention": params.human_intervention,
            "affected_work_units": sorted(set(params.affected_work_unit)),
        },
        "evidence_refs": sorted(set(params.evidence_ref)),
        "workaround": params.workaround,
        "candidate_improvement": params.candidate_improvement,
        "recurrence_key": params.recurrence_key,
        "status": params.status,
        "resolution": params.resolution,
    }
    common.validate_payload(workspace, payload, "observation.schema.json")
    return payload


def _scoped_objects(workspace: Workspace, directory: str, work_unit_id: str | None) -> list[dict]:
    return [
        payload
        for _path, payload in common.load_yaml_directory(workspace.ai_team / directory)
        if common.relates_to_work_unit(payload, work_unit_id)
    ]


def generate_retrospective(
    workspace: Workspace, params: RetrospectiveParams
) -> RetrospectiveResult:
    meta = common.metadata(workspace)
    work_unit_id = params.work_unit
    work_units = []
    if work_unit_id:
        found = common.find_work_unit(workspace, work_unit_id)
        if found is None:
            raise ValueError(f"Work Unit not found: {work_unit_id}")
        work_units = [found[1]]
        scope_type = "work_unit"
        scope_ref = work_unit_id
    else:
        work_units = [
            data for _path, data in common.load_yaml_directory(workspace.ai_team / "work-units")
        ]
        scope_type = "project"
        scope_ref = meta["project_id"]

    observations = _scoped_objects(workspace, "observations", work_unit_id)
    events = _scoped_objects(workspace, "events", work_unit_id)
    decisions = _scoped_objects(workspace, "decisions", work_unit_id)
    findings = _scoped_objects(workspace, "findings", work_unit_id)
    acceptances = _scoped_objects(workspace, "acceptance", work_unit_id)
    summary, signals = common.observation_summary(observations)
    signals["event_types"] = dict(
        sorted(Counter(item.get("type", "unknown") for item in events).items())
    )
    signals["work_unit_statuses"] = dict(
        sorted(Counter(item.get("status", "unknown") for item in work_units).items())
    )
    unresolved = {"open", "acknowledged", "candidate_change"}

    retrospective_id = common.generated_id("RET")
    payload = {
        "id": retrospective_id,
        "generated_at": common.now_iso(),
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
        "notes": params.notes,
        "status": "generated",
    }
    common.validate_payload(workspace, payload, "retrospective.schema.json")
    path = (
        Path(params.output).expanduser().resolve()
        if params.output
        else workspace.ai_team / "retrospectives" / f"{retrospective_id}.yaml"
    )
    common.atomic_write_yaml(path, payload)
    try:
        display_path = path.relative_to(workspace.root)
    except ValueError:
        display_path = path
    return RetrospectiveResult(
        retrospective_id=retrospective_id,
        path=path,
        display_path=display_path,
    )


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


def export_feedback(workspace: Workspace, params: ExportParams) -> ExportResult:
    meta = common.metadata(workspace)
    observations = [
        data for _path, data in common.load_yaml_directory(workspace.ai_team / "observations")
    ]
    retrospectives = [
        data for _path, data in common.load_yaml_directory(workspace.ai_team / "retrospectives")
    ]
    summary, signals = common.observation_summary(observations)
    summary["signals"] = signals
    summary["retrospectives"] = len(retrospectives)
    project_ref = _hash_ref(meta["project_id"])

    if params.detail_level == "aggregate":
        exported_observations = []
        exported_retrospectives = []
    elif params.detail_level == "structured":
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
            _full_without_project_id(item, project_ref, params.include_project_id)
            for item in observations
        ]
        exported_retrospectives = [
            _full_without_project_id(item, project_ref, params.include_project_id)
            for item in retrospectives
        ]

    payload = {
        "format_version": "1.0",
        "generated_at": common.now_iso(),
        "detail_level": params.detail_level,
        "project_ref": project_ref,
        "framework_version": meta["framework_version"],
        "constitution_version": meta["constitution_version"],
        "summary": summary,
        "observations": exported_observations,
        "retrospectives": exported_retrospectives,
    }
    if params.include_project_id:
        payload["project_id"] = meta["project_id"]
    common.validate_payload(workspace, payload, "feedback-export.schema.json")
    timestamp = common.now_iso().replace(":", "").replace("+00:00", "Z")
    path = (
        Path(params.output).expanduser().resolve()
        if params.output
        else workspace.ai_team / "metrics" / f"framework-feedback-{timestamp}.json"
    )
    common.atomic_write_json(path, payload)
    try:
        display_path = path.relative_to(workspace.root)
    except ValueError:
        display_path = path
    return ExportResult(
        path=path,
        display_path=display_path,
        detail_level=params.detail_level,
        show_full_warning=params.detail_level == "full",
    )
