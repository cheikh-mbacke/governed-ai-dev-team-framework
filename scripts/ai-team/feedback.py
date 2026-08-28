#!/usr/bin/env python3
"""Record, summarize, and export structured framework-learning feedback."""

from __future__ import annotations

import argparse
import sys

try:
    from feedback_common import ROOT
except ModuleNotFoundError:
    print("Missing dependency: PyYAML and/or jsonschema. Install requirements first.")
    raise SystemExit(1)

from governed_ai.core.workspace import Workspace
from governed_ai.feedback import commands

from i18n import project_language, t

LANG = project_language(ROOT)
WORKSPACE = Workspace.from_root(ROOT)

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
    result = commands.record_observation(
        WORKSPACE,
        commands.RecordObservationParams(
            category=args.category,
            symptom=args.symptom,
            severity=args.severity,
            origin=args.origin,
            confidence=args.confidence,
            work_unit=args.work_unit,
            phase=args.phase,
            recorded_by=args.recorded_by,
            blocked_minutes=args.blocked_minutes,
            rework_required=args.rework_required,
            human_intervention=args.human_intervention,
            affected_work_unit=tuple(args.affected_work_unit),
            evidence_ref=tuple(args.evidence_ref),
            workaround=args.workaround,
            candidate_improvement=args.candidate_improvement,
            recurrence_key=args.recurrence_key,
            status=args.status,
            resolution=args.resolution,
        ),
    )
    print(
        t(
            LANG,
            f"Recorded {result.observation_id}: {result.display_path}",
            f"Enregistre {result.observation_id} : {result.display_path}",
        )
    )
    return 0


def generate_retrospective(args: argparse.Namespace) -> int:
    result = commands.generate_retrospective(
        WORKSPACE,
        commands.RetrospectiveParams(
            work_unit=args.work_unit,
            project=args.project,
            notes=args.notes,
            output=args.output,
        ),
    )
    print(
        t(
            LANG,
            f"Generated {result.retrospective_id}: {result.display_path}",
            f"Genere {result.retrospective_id} : {result.display_path}",
        )
    )
    return 0


def export_feedback(args: argparse.Namespace) -> int:
    result = commands.export_feedback(
        WORKSPACE,
        commands.ExportParams(
            detail_level=args.detail_level,
            include_project_id=args.include_project_id,
            output=args.output,
        ),
    )
    print(
        t(
            LANG,
            f"Exported {result.detail_level} feedback: {result.display_path}",
            f"Export {result.detail_level} genere : {result.display_path}",
        )
    )
    if result.show_full_warning:
        print(
            t(
                LANG,
                "WARNING: full exports may contain project-sensitive free text and references.",
                "ATTENTION : un export complet peut contenir du texte libre et des references sensibles au projet.",
            )
        )
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
        print(t(LANG, f"ERROR: {exc}", f"ERREUR : {exc}"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
