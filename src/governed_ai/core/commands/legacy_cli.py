"""Legacy CLI argument translation into Command Envelopes (Document 13 §6–§7)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from governed_ai.compat.datetime import UTC, datetime

DEPRECATION_RECORD_GATE = (
    "DEPRECATED: use scripts/ai-team/gov.py command with RecordGateDecision; "
    "use scripts/ai-team/gov.py command with a Command Envelope."
)
DEPRECATION_FEEDBACK = (
    "DEPRECATED: scripts/ai-team/feedback.py direct writes are replaced by the "
    "Command Gateway; this wrapper translates legacy arguments automatically."
)

GATE_CHOICES = frozenset({"G0", "G1", "G2", "G3", "G4"})
GATE_STATUS_CHOICES = frozenset(
    {
        "approved",
        "rejected",
        "changes_requested",
        "passed",
        "failed",
        "partial",
        "partially_accepted",
        "not_required",
        "accepted",
        "remediation_required",
    }
)
FEEDBACK_CATEGORIES = frozenset(
    {
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
    }
)
FEEDBACK_SEVERITIES = frozenset({"info", "low", "medium", "high", "critical"})
FEEDBACK_ORIGINS = frozenset(
    {"framework", "project", "environment", "external_service", "human_process", "unknown"}
)
FEEDBACK_CONFIDENCES = frozenset({"low", "probable", "high", "confirmed"})
FEEDBACK_STATUSES = frozenset(
    {"open", "acknowledged", "candidate_change", "resolved", "rejected"}
)
EXPORT_DETAIL_LEVELS = frozenset({"aggregate", "structured", "full"})
FRENCH_MARKERS = frozenset({"français", "francais", "french", "fr", "fr-fr"})


def _is_french(language: str) -> bool:
    return (language or "").strip().lower() in FRENCH_MARKERS


class TranslationError(ValueError):
    """Legacy arguments cannot be converted into a Command Envelope."""


@dataclass(frozen=True, slots=True)
class RecordGateArgs:
    gate: str
    status: str
    by: str
    note: str = ""
    work_unit: str = ""
    authorization_id: str = ""
    authorization_granted_by: str = ""
    authorization_scope: str = ""


@dataclass(frozen=True, slots=True)
class FeedbackRecordArgs:
    category: str
    symptom: str
    severity: str = "medium"
    origin: str = "unknown"
    confidence: str = "low"
    work_unit: str | None = None
    phase: str | None = None
    recorded_by: str | None = None
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
class FeedbackRetrospectiveArgs:
    work_unit: str | None = None
    project: bool = False
    notes: str | None = None
    output: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackExportArgs:
    detail_level: str = "structured"
    include_project_id: bool = False
    output: str | None = None
    authorization_id: str = ""
    authorization_granted_by: str = ""
    authorization_scope: str = "export:full"


@dataclass(frozen=True, slots=True)
class FeedbackSubmitArgs:
    output: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackTransitionArgs:
    observation_id: str
    to_status: str
    expected_revision: int
    resolution: str | None = None
    origin: str | None = None
    confidence: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _command_ids(prefix: str) -> tuple[str, str, str]:
    suffix = uuid.uuid4().hex[:12]
    command_id = f"CMD-{prefix}-{suffix}"
    return command_id, f"idem-{prefix}-{suffix}", f"COR-{prefix}-{suffix}"


def _resolve_active_adapter_id() -> str:
    """Read active_adapter_id from the project profile when available."""
    profile_path = Path.cwd() / ".ai-team" / "project-profile.yaml"
    if not profile_path.is_file():
        return "unspecified"
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return "unspecified"
    if not isinstance(data, dict):
        return "unspecified"
    adapter_id = data.get("active_adapter_id")
    if isinstance(adapter_id, str) and adapter_id.strip():
        return adapter_id.strip()
    return "unspecified"


def _base_envelope(*, command_type: str, prefix: str, actor_role: str) -> dict[str, Any]:
    command_id, idempotency_key, correlation_id = _command_ids(prefix)
    return {
        "protocol_version": "1.0",
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "type": command_type,
        "issued_at": _now_iso(),
        "actor": {
            "kind": "role",
            "execution_id": f"EXE-{prefix}",
            "role_id": actor_role,
            "bundle_version": "1.0.0",
            "adapter_id": _resolve_active_adapter_id(),
        },
    }


def _human_authorization(
    *,
    authorization_id: str,
    granted_by: str,
    scope: str,
) -> dict[str, str | None]:
    return {
        "authorization_id": authorization_id,
        "granted_by": granted_by,
        "granted_at": _now_iso(),
        "scope": scope,
        "consumed_at": None,
    }


def translate_record_gate(args: RecordGateArgs) -> dict[str, Any]:
    if args.gate not in GATE_CHOICES:
        raise TranslationError(f"unsupported gate {args.gate!r}")
    if args.status not in GATE_STATUS_CHOICES:
        raise TranslationError(f"unsupported gate status {args.status!r}")
    if not args.by.strip():
        raise TranslationError("--by is required")
    if not args.authorization_id.strip():
        raise TranslationError(
            "--authorization-id is required to record a gate decision via the Command Gateway"
        )

    envelope = _base_envelope(
        command_type="RecordGateDecision",
        prefix="legacy-gate",
        actor_role="control-plane",
    )
    envelope["target"] = {"kind": "gate_decision", "id": "new"}
    payload: dict[str, Any] = {
        "gate": args.gate,
        "status": args.status,
        "by": args.by,
        "note": args.note,
    }
    if args.work_unit.strip():
        work_unit_ids = [item.strip() for item in args.work_unit.split(",") if item.strip()]
        if work_unit_ids:
            payload["work_unit_ids"] = work_unit_ids
    envelope["payload"] = payload
    envelope["human_authorization"] = _human_authorization(
        authorization_id=args.authorization_id.strip(),
        granted_by=(args.authorization_granted_by or args.by).strip(),
        scope=(args.authorization_scope or f"gate:{args.gate}").strip(),
    )
    return envelope


def translate_feedback_record(args: FeedbackRecordArgs) -> dict[str, Any]:
    if args.category not in FEEDBACK_CATEGORIES:
        raise TranslationError(f"unsupported category {args.category!r}")
    if args.severity not in FEEDBACK_SEVERITIES:
        raise TranslationError(f"unsupported severity {args.severity!r}")
    if args.origin not in FEEDBACK_ORIGINS:
        raise TranslationError(f"unsupported origin {args.origin!r}")
    if args.confidence not in FEEDBACK_CONFIDENCES:
        raise TranslationError(f"unsupported confidence {args.confidence!r}")
    if args.status not in FEEDBACK_STATUSES:
        raise TranslationError(f"unsupported status {args.status!r}")
    if not args.symptom.strip():
        raise TranslationError("--symptom is required")
    if args.blocked_minutes < 0:
        raise TranslationError("--blocked-minutes cannot be negative")

    actor_role = (args.recorded_by or "code-reviewer").strip()
    envelope = _base_envelope(
        command_type="RecordObservation",
        prefix="legacy-feedback-record",
        actor_role=actor_role,
    )
    envelope["target"] = {"kind": "observation", "id": "new"}
    envelope["payload"] = {
        "category": args.category,
        "symptom": args.symptom,
        "severity": args.severity,
        "classification": {"origin": args.origin, "confidence": args.confidence},
        "work_unit": args.work_unit,
        "phase": args.phase,
        "recorded_by": args.recorded_by,
        "impact": {
            "blocked_minutes": args.blocked_minutes,
            "rework_required": args.rework_required,
            "human_intervention": args.human_intervention,
            "affected_work_units": list(args.affected_work_unit),
        },
        "evidence_refs": list(args.evidence_ref),
        "workaround": args.workaround,
        "candidate_improvement": args.candidate_improvement,
        "recurrence_key": args.recurrence_key,
        "status": args.status,
        "resolution": args.resolution,
    }
    return envelope


def translate_feedback_retrospective(args: FeedbackRetrospectiveArgs) -> dict[str, Any]:
    if args.project and args.work_unit:
        raise TranslationError("use either --work-unit or --project, not both")
    if not args.project and not args.work_unit:
        raise TranslationError("either --work-unit or --project is required")

    envelope = _base_envelope(
        command_type="GenerateRetrospective",
        prefix="legacy-feedback-retro",
        actor_role="control-plane",
    )
    envelope["target"] = {"kind": "retrospective", "id": "new"}
    if args.project:
        payload: dict[str, Any] = {"scope": "project"}
    else:
        payload = {"scope": "work_unit", "work_unit_id": args.work_unit}
    if args.notes:
        payload["notes"] = args.notes
    if args.output:
        payload["output"] = args.output
    envelope["payload"] = payload
    return envelope


def _telemetry_collection() -> str:
    profile_path = Path.cwd() / ".ai-team" / "project-profile.yaml"
    if not profile_path.is_file():
        return "consented_share"
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return "consented_share"
    if not isinstance(data, dict):
        return "consented_share"
    telemetry = data.get("telemetry") or {}
    if not isinstance(telemetry, dict):
        return "consented_share"
    collection = telemetry.get("collection")
    if isinstance(collection, str) and collection.strip():
        return collection.strip()
    return "consented_share"


def translate_feedback_export(args: FeedbackExportArgs) -> dict[str, Any]:
    if args.detail_level not in EXPORT_DETAIL_LEVELS:
        raise TranslationError(f"unsupported detail level {args.detail_level!r}")

    envelope = _base_envelope(
        command_type="ExportFeedback",
        prefix="legacy-feedback-export",
        actor_role="control-plane",
    )
    envelope["target"] = {"kind": "feedback_export", "id": "new"}
    payload: dict[str, Any] = {
        "detail_level": args.detail_level,
        "include_project_id": args.include_project_id,
    }
    if args.output:
        payload["output"] = args.output
    envelope["payload"] = payload
    # ADR-009: installing/using the framework is acceptance — no export auth gate.
    return envelope

def translate_feedback_submit(args: FeedbackSubmitArgs) -> dict[str, Any]:
    envelope = _base_envelope(
        command_type="SubmitFeedback",
        prefix="legacy-feedback-submit",
        actor_role="control-plane",
    )
    envelope["target"] = {"kind": "feedback_export", "id": "new"}
    payload: dict[str, Any] = {}
    if args.output:
        payload["output"] = args.output
    envelope["payload"] = payload
    return envelope


def translate_feedback_transition(args: FeedbackTransitionArgs) -> dict[str, Any]:
    if args.to_status not in FEEDBACK_STATUSES:
        raise TranslationError(f"unsupported status {args.to_status!r}")
    if args.expected_revision < 1:
        raise TranslationError("expected-revision must be >= 1")
    if (args.origin is None) ^ (args.confidence is None):
        raise TranslationError("provide both --origin and --confidence, or neither")
    if args.origin is not None and args.origin not in FEEDBACK_ORIGINS:
        raise TranslationError(f"unsupported origin {args.origin!r}")
    if args.confidence is not None and args.confidence not in FEEDBACK_CONFIDENCES:
        raise TranslationError(f"unsupported confidence {args.confidence!r}")
    if args.to_status in {"resolved", "rejected"} and not (args.resolution or "").strip():
        raise TranslationError("--resolution is required for resolved/rejected")

    envelope = _base_envelope(
        command_type="TransitionObservation",
        prefix="legacy-feedback-transition",
        actor_role="control-plane",
    )
    envelope["target"] = {
        "kind": "observation",
        "id": args.observation_id,
        "expected_revision": args.expected_revision,
    }
    payload: dict[str, Any] = {"to_status": args.to_status}
    if args.resolution is not None:
        payload["resolution"] = args.resolution
    if args.origin is not None and args.confidence is not None:
        payload["classification"] = {
            "origin": args.origin,
            "confidence": args.confidence,
        }
    envelope["payload"] = payload
    return envelope


def format_record_gate_stdout(receipt: dict[str, Any], *, by: str) -> list[str]:
    lines: list[str] = []
    gate = None
    status = None
    for item in receipt.get("affected") or []:
        if item.get("kind") == "gate_decision":
            gate = item.get("gate")
            status = item.get("status")
            break
    if gate and status:
        lines.append(f"Recorded {gate}={status} by {by}")
    work_units = [
        item for item in receipt.get("affected") or [] if item.get("kind") == "work_unit"
    ]
    for item in work_units:
        lines.append(
            f"  Updated {item['id']}.yaml: outcomes.human_acceptance = {item.get('human_acceptance')}"
        )
    if gate == "G4" and not work_units:
        lines.extend(
            [
                "  NOTE: no --work-unit given. This recorded the gate at the project level only -",
                "  it did NOT mark any specific Work Unit's human_acceptance. If a Work Unit needs",
                "  that recorded too, re-run with --work-unit WU-XXX, or check_done.py will still",
                "  report it as NOT DONE.",
            ]
        )
    if gate == "G4" and work_units:
        lines.append(
            "  Run python scripts/ai-team/check_done.py <WU-ID> to confirm each Work Unit's "
            "overall Definition of Done."
        )
    return lines


def format_feedback_record_stdout(receipt: dict[str, Any], *, lang: str) -> str:
    observation_id = None
    coalesced = False
    occurrence_count = 1
    for item in receipt.get("affected") or []:
        if item.get("kind") == "observation":
            observation_id = item.get("id")
            coalesced = bool(item.get("coalesced"))
            occurrence_count = int(item.get("occurrence_count") or 1)
            break
    if not observation_id:
        raise TranslationError("gateway receipt missing observation id")
    rel_path = Path(".ai-team") / "observations" / f"{observation_id}.yaml"
    if coalesced:
        if _is_french(lang):
            return (
                f"Mis a jour {observation_id} (occurrences={occurrence_count}) : {rel_path}\n"
            )
        return f"Updated {observation_id} (occurrences={occurrence_count}): {rel_path}\n"
    if _is_french(lang):
        return f"Enregistre {observation_id} : {rel_path}\n"
    return f"Recorded {observation_id}: {rel_path}\n"


def format_feedback_transition_stdout(receipt: dict[str, Any], *, lang: str) -> str:
    observation_id = None
    status = None
    from_status = None
    revision = None
    for item in receipt.get("affected") or []:
        if item.get("kind") == "observation":
            observation_id = item.get("id")
            status = item.get("status")
            from_status = item.get("from_status")
            revision = item.get("revision")
            break
    if not observation_id or not status:
        raise TranslationError("gateway receipt missing observation transition")
    if _is_french(lang):
        return (
            f"Transition {observation_id} : {from_status} -> {status} "
            f"(revision={revision})\n"
        )
    return (
        f"Transitioned {observation_id}: {from_status} -> {status} "
        f"(revision={revision})\n"
    )


def format_feedback_retrospective_stdout(receipt: dict[str, Any], *, lang: str) -> str:
    retro_id = None
    rel_path = None
    for item in receipt.get("affected") or []:
        if item.get("kind") == "retrospective":
            retro_id = item.get("id")
            rel_path = item.get("path")
            break
    if not retro_id or not rel_path:
        raise TranslationError("gateway receipt missing retrospective metadata")
    display = rel_path.replace("/", "\\")
    if _is_french(lang):
        return f"Genere {retro_id} : {display}\n"
    return f"Generated {retro_id}: {display}\n"


def format_feedback_export_stdout(receipt: dict[str, Any], *, lang: str) -> tuple[str, bool]:
    detail_level = "structured"
    rel_path = None
    transmission_status = None
    submitted = False
    for item in receipt.get("affected") or []:
        if item.get("kind") == "feedback_export":
            detail_level = item.get("detail_level", detail_level)
            rel_path = item.get("path")
            transmission_status = item.get("transmission_status")
            submitted = bool(item.get("submitted"))
            break
    if not rel_path:
        raise TranslationError("gateway receipt missing export path")
    display = rel_path.replace("/", "\\")
    if submitted:
        if _is_french(lang):
            line = (
                f"Feedback soumis ({detail_level}, transmission={transmission_status}) : {display}\n"
            )
        else:
            line = (
                f"Submitted {detail_level} feedback "
                f"(transmission={transmission_status}): {display}\n"
            )
        return line, False
    if _is_french(lang):
        line = f"Export {detail_level} genere : {display}\n"
    else:
        line = f"Exported {detail_level} feedback: {display}\n"
    return line, detail_level == "full" and not submitted
