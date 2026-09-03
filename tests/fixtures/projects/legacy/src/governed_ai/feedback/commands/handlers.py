"""Feedback command handlers (record, retrospective, export)."""

from __future__ import annotations

import hashlib
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from governed_ai.core.workspace import Workspace
from governed_ai.feedback import common
from governed_ai.feedback.domain.observation import (
    UNRESOLVED_STATUSES,
    apply_coalesce,
    find_coalesce_candidate,
    normalize_recurrence_key,
    occurrence_count_of,
)


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
    coalesced: bool = False
    occurrence_count: int = 1


@dataclass(frozen=True, slots=True)
class PreparedObservation:
    document: dict
    path: Path
    coalesced: bool


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
    prepared = prepare_observation_write(workspace, params)
    if not prepared.coalesced and prepared.path.is_file():
        raise ValueError(f"observation {prepared.document['id']!r} already exists")
    common.atomic_write_yaml(prepared.path, prepared.document)
    return RecordObservationResult(
        observation_id=prepared.document["id"],
        path=prepared.path,
        display_path=prepared.path.relative_to(workspace.root),
        coalesced=prepared.coalesced,
        occurrence_count=occurrence_count_of(prepared.document),
    )


def prepare_observation_write(
    workspace: Workspace, params: RecordObservationParams
) -> PreparedObservation:
    """Create a new Observation or fold it into an unresolved recurrence."""
    if params.blocked_minutes < 0:
        raise ValueError("--blocked-minutes cannot be negative")
    if params.work_unit and common.find_work_unit(workspace, params.work_unit) is None:
        raise ValueError(f"Work Unit not found: {params.work_unit}")
    for work_unit in params.affected_work_unit:
        if common.find_work_unit(workspace, work_unit) is None:
            raise ValueError(f"Affected Work Unit not found: {work_unit}")

    key = normalize_recurrence_key(params.recurrence_key)
    if key:
        loaded = common.load_yaml_directory(workspace.ai_team / "observations")
        candidate = find_coalesce_candidate(
            loaded, recurrence_key=key, work_unit=params.work_unit
        )
        if candidate is not None:
            path, existing = candidate
            document = apply_coalesce(
                existing,
                now=common.now_iso(),
                blocked_minutes=params.blocked_minutes,
                rework_required=params.rework_required,
                human_intervention=params.human_intervention,
                affected_work_units=params.affected_work_unit,
                evidence_refs=params.evidence_ref,
                severity=params.severity,
                workaround=params.workaround,
                candidate_improvement=params.candidate_improvement,
            )
            common.validate_payload(workspace, document, "observation.schema.json")
            return PreparedObservation(document=document, path=path, coalesced=True)

    document = build_observation_document(workspace, params)
    path = workspace.ai_team / "observations" / f"{document['id']}.yaml"
    return PreparedObservation(document=document, path=path, coalesced=False)


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
    recorded_at = common.now_iso()
    payload = {
        "id": observation_id,
        "recorded_at": recorded_at,
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
        "occurrence_count": 1,
        "last_recorded_at": recorded_at,
        "revision": 1,
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


def build_retrospective_document(
    workspace: Workspace, params: RetrospectiveParams
) -> tuple[dict, Path]:
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
    attempts = _execution_attempts(workspace, work_unit_id)
    summary, signals = common.observation_summary(observations)
    signals["event_types"] = dict(
        sorted(Counter(item.get("type", "unknown") for item in events).items())
    )
    signals["work_unit_statuses"] = dict(
        sorted(Counter(item.get("status", "unknown") for item in work_units).items())
    )
    signals["executions"] = _execution_summary(attempts)

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
            item["id"] for item in observations if item.get("status") in UNRESOLVED_STATUSES
        ],
        "notes": params.notes,
        "status": "generated",
        "revision": 1,
        "reviewed_at": None,
        "reviewed_by": None,
    }
    common.validate_payload(workspace, payload, "retrospective.schema.json")
    if params.output:
        path = Path(params.output).expanduser().resolve()
    else:
        path = workspace.ai_team / "retrospectives" / f"{retrospective_id}.yaml"
    return payload, path


def generate_retrospective(
    workspace: Workspace, params: RetrospectiveParams
) -> RetrospectiveResult:
    payload, path = build_retrospective_document(workspace, params)
    common.atomic_write_yaml(path, payload)
    try:
        display_path = path.relative_to(workspace.root)
    except ValueError:
        display_path = path
    return RetrospectiveResult(
        retrospective_id=payload["id"],
        path=path,
        display_path=display_path,
    )


def _hash_ref(value: str | None, *, namespace: str = "") -> str:
    source = f"{namespace}:{value or 'unknown'}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _structured_observation(item: dict, *, project_ref: str) -> dict:
    recurrence = item.get("recurrence_key")
    impact = item.get("impact") or {}
    return {
        "observation_ref": _hash_ref(item.get("id"), namespace=project_ref),
        "category": item.get("category"),
        "severity": item.get("severity"),
        "origin": (item.get("classification") or {}).get("origin"),
        "confidence": (item.get("classification") or {}).get("confidence"),
        "impact": {
            "blocked_minutes": int(impact.get("blocked_minutes") or 0),
            "rework_required": bool(impact.get("rework_required")),
            "human_intervention": bool(impact.get("human_intervention")),
            "affected_work_unit_count": len(impact.get("affected_work_units") or []),
        },
        "recurrence_ref": (
            _hash_ref(recurrence, namespace=project_ref) if recurrence else None
        ),
        "occurrence_count": occurrence_count_of(item),
        "status": item.get("status"),
    }


def _execution_attempts(workspace: Workspace, work_unit_id: str | None = None) -> list[dict]:
    attempts = [
        data
        for _path, data in common.load_yaml_directory(
            workspace.ai_team / "runs" / "execution-attempts"
        )
    ]
    if work_unit_id is not None:
        attempts = [item for item in attempts if item.get("work_unit_id") == work_unit_id]
    return attempts


def _duration_ms(item: dict) -> int:
    explicit = item.get("duration_ms")
    if isinstance(explicit, int) and explicit >= 0:
        return explicit
    try:
        started = datetime.fromisoformat(str(item["started_at"]).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(item["ended_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return 0
    return max(0, int((ended - started).total_seconds() * 1000))


def _execution_summary(attempts: list[dict]) -> dict:
    terminal = [item for item in attempts if item.get("status") != "started"]
    return {
        "total": len(attempts),
        "terminal": len(terminal),
        "by_status": dict(
            sorted(Counter(item.get("status", "unknown") for item in attempts).items())
        ),
        "by_step": dict(
            sorted(Counter(item.get("step", "unknown") for item in attempts).items())
        ),
        "duration_ms": sum(_duration_ms(item) for item in terminal),
        "input_tokens": sum(
            int((item.get("usage") or {}).get("input_tokens", 0) or 0) for item in terminal
        ),
        "output_tokens": sum(
            int((item.get("usage") or {}).get("output_tokens", 0) or 0) for item in terminal
        ),
        "total_tokens": sum(
            int((item.get("usage") or {}).get("total_tokens", 0) or 0) for item in terminal
        ),
        "cost": sum(
            float((item.get("usage") or {}).get("cost", 0) or 0) for item in terminal
        ),
    }


def _structured_execution(item: dict, *, project_ref: str) -> dict:
    usage = item.get("usage") or {}
    contract = item.get("contract") or {}
    return {
        "attempt_ref": _hash_ref(item.get("id"), namespace=project_ref),
        "execution_ref": _hash_ref(item.get("execution_id"), namespace=project_ref),
        "run_ref": _hash_ref(item.get("run_id"), namespace=project_ref),
        "work_unit_ref": _hash_ref(item.get("work_unit_id"), namespace=project_ref),
        "step": item.get("step"),
        "status": item.get("status"),
        "duration_ms": _duration_ms(item),
        "role_id": contract.get("role_id"),
        "procedure_id": contract.get("procedure_id"),
        "model": (item.get("provider") or {}).get("model"),
        "usage": {
            key: usage[key]
            for key in ("input_tokens", "output_tokens", "total_tokens", "cost", "currency")
            if key in usage
        },
    }


def _full_without_project_id(item: dict, project_ref: str, include_id: bool) -> dict:
    result = deepcopy(item)
    if not include_id:
        result.pop("project_id", None)
        result["project_ref"] = project_ref
        if (result.get("scope") or {}).get("type") == "project":
            result["scope"]["ref"] = project_ref
    return result


def build_export_document(workspace: Workspace, params: ExportParams) -> tuple[dict, Path]:
    meta = common.metadata(workspace)
    # ADR-009: using the framework means full remount — no anonymized half-measure.
    sharing = meta.get("telemetry_collection") != "disabled"
    detail_level = params.detail_level
    include_project_id = params.include_project_id
    if sharing:
        detail_level = "full"
        include_project_id = True

    observations = [
        data for _path, data in common.load_yaml_directory(workspace.ai_team / "observations")
    ]
    retrospectives = [
        data for _path, data in common.load_yaml_directory(workspace.ai_team / "retrospectives")
    ]
    attempts = _execution_attempts(workspace)
    summary, signals = common.observation_summary(observations)
    summary["signals"] = signals
    summary["retrospectives"] = len(retrospectives)
    summary["executions"] = _execution_summary(attempts)
    project_ref = meta.get("telemetry_project_ref") or (
        "LEGACY-" + _hash_ref(meta["project_id"], namespace="legacy-project")
    )

    if detail_level == "aggregate":
        exported_observations = []
        exported_retrospectives = []
        exported_executions = []
    elif detail_level == "structured":
        exported_observations = [
            _structured_observation(item, project_ref=project_ref) for item in observations
        ]
        exported_retrospectives = [
            {
                "retrospective_ref": _hash_ref(item.get("id"), namespace=project_ref),
                "scope_type": (item.get("scope") or {}).get("type"),
                "observation_summary": item.get("observation_summary") or {},
                "signals": item.get("signals") or {},
                "status": item.get("status"),
            }
            for item in retrospectives
        ]
        exported_executions = [
            _structured_execution(item, project_ref=project_ref) for item in attempts
        ]
    else:
        exported_observations = [
            _full_without_project_id(item, project_ref, include_project_id)
            for item in observations
        ]
        exported_retrospectives = [
            _full_without_project_id(item, project_ref, include_project_id)
            for item in retrospectives
        ]
        exported_executions = [
            _full_without_project_id(item, project_ref, include_project_id)
            for item in attempts
        ]

    payload = {
        "format_version": "1.2",
        "export_id": common.generated_id("EXP"),
        "generated_at": common.now_iso(),
        "detail_level": detail_level,
        "project_ref": project_ref,
        "framework_version": meta["framework_version"],
        "constitution_version": meta["constitution_version"],
        "summary": summary,
        "observations": exported_observations,
        "retrospectives": exported_retrospectives,
        "executions": exported_executions,
        "transmission": {
            "status": "pending",
            "submitted_at": None,
            "destination": None,
            "ack_id": None,
            "error": None,
        },
    }
    if include_project_id:
        payload["project_id"] = meta["project_id"]
    common.validate_payload(workspace, payload, "feedback-export.schema.json")
    if params.output:
        path = Path(params.output).expanduser().resolve()
    else:
        timestamp = common.now_iso().replace(":", "").replace("+00:00", "Z")
        path = workspace.ai_team / "metrics" / f"framework-feedback-{timestamp}.json"
    return payload, path


def export_feedback(workspace: Workspace, params: ExportParams) -> ExportResult:
    payload, path = build_export_document(workspace, params)
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
