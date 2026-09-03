#!/usr/bin/env python3
"""Record, summarize, and export structured framework-learning feedback."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

try:
    import yaml  # noqa: F401 — ensure feedback dependencies are present
except ModuleNotFoundError:
    print("Missing dependency: PyYAML and/or jsonschema. Install requirements first.", file=sys.stderr)
    raise SystemExit(1) from None

from i18n import project_language, t

from governed_ai.core.commands.errors import EXIT_CLI
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.commands.legacy_cli import (
    DEPRECATION_FEEDBACK,
    FeedbackExportArgs,
    FeedbackRecordArgs,
    FeedbackRetrospectiveArgs,
    FeedbackSubmitArgs,
    TranslationError,
    format_feedback_export_stdout,
    format_feedback_record_stdout,
    format_feedback_retrospective_stdout,
    translate_feedback_export,
    translate_feedback_record,
    translate_feedback_retrospective,
    translate_feedback_submit,
)
from governed_ai.core.workspace import Workspace

ROOT = Workspace.discover(Path.cwd()).root
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
    export.add_argument("--authorization-id", default="")
    export.add_argument("--authorization-granted-by", default="")
    export.add_argument("--authorization-scope", default="export:full")

    submit = subparsers.add_parser(
        "submit",
        help="submit full consented feedback to the framework learning ingest (ADR-009)",
    )
    submit.add_argument("--output")
    return parser


def _execute(envelope: dict) -> tuple[dict, int]:
    gateway = CommandGateway(WORKSPACE)
    return gateway.execute_command(envelope)


def _handle_gateway_failure(receipt: dict, exit_code: int) -> None:
    errors = receipt.get("errors") or []
    message = errors[0]["message"] if errors else "gateway rejected the command"
    print(t(LANG, f"GATEWAY ERROR: {message}", f"ERREUR GATEWAY : {message}"), file=sys.stderr)
    raise SystemExit(exit_code)


def record_observation(args: argparse.Namespace) -> int:
    print(DEPRECATION_FEEDBACK, file=sys.stderr)
    try:
        envelope = translate_feedback_record(
            FeedbackRecordArgs(
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
            )
        )
    except TranslationError as exc:
        print(t(LANG, f"WRAPPER TRANSLATION ERROR: {exc}", f"ERREUR TRADUCTION WRAPPER : {exc}"), file=sys.stderr)
        return EXIT_CLI

    receipt, exit_code = _execute(envelope)
    if exit_code != 0:
        _handle_gateway_failure(receipt, exit_code)
    print(format_feedback_record_stdout(receipt, lang=LANG), end="")
    return 0


def generate_retrospective(args: argparse.Namespace) -> int:
    print(DEPRECATION_FEEDBACK, file=sys.stderr)
    try:
        envelope = translate_feedback_retrospective(
            FeedbackRetrospectiveArgs(
                work_unit=args.work_unit,
                project=args.project,
                notes=args.notes,
                output=args.output,
            )
        )
    except TranslationError as exc:
        print(t(LANG, f"WRAPPER TRANSLATION ERROR: {exc}", f"ERREUR TRADUCTION WRAPPER : {exc}"), file=sys.stderr)
        return EXIT_CLI

    receipt, exit_code = _execute(envelope)
    if exit_code != 0:
        _handle_gateway_failure(receipt, exit_code)
    print(format_feedback_retrospective_stdout(receipt, lang=LANG), end="")
    return 0


def export_feedback(args: argparse.Namespace) -> int:
    print(DEPRECATION_FEEDBACK, file=sys.stderr)
    try:
        envelope = translate_feedback_export(
            FeedbackExportArgs(
                detail_level=args.detail_level,
                include_project_id=args.include_project_id,
                output=args.output,
                authorization_id=args.authorization_id,
                authorization_granted_by=args.authorization_granted_by,
                authorization_scope=args.authorization_scope,
            )
        )
    except TranslationError as exc:
        print(t(LANG, f"WRAPPER TRANSLATION ERROR: {exc}", f"ERREUR TRADUCTION WRAPPER : {exc}"), file=sys.stderr)
        return EXIT_CLI

    receipt, exit_code = _execute(envelope)
    if exit_code != 0:
        _handle_gateway_failure(receipt, exit_code)
    line, show_full_warning = format_feedback_export_stdout(receipt, lang=LANG)
    print(line, end="")
    if show_full_warning:
        print(
            t(
                LANG,
                "WARNING: full exports may contain project-sensitive free text and references.",
                "ATTENTION : un export complet peut contenir du texte libre et des references sensibles au projet.",
            )
        )
    return 0


def submit_feedback(args: argparse.Namespace) -> int:
    print(DEPRECATION_FEEDBACK, file=sys.stderr)
    try:
        envelope = translate_feedback_submit(FeedbackSubmitArgs(output=args.output))
    except TranslationError as exc:
        print(t(LANG, f"WRAPPER TRANSLATION ERROR: {exc}", f"ERREUR TRADUCTION WRAPPER : {exc}"), file=sys.stderr)
        return EXIT_CLI

    receipt, exit_code = _execute(envelope)
    if exit_code != 0:
        _handle_gateway_failure(receipt, exit_code)
    line, _show_warning = format_feedback_export_stdout(receipt, lang=LANG)
    print(line, end="")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "record":
        return record_observation(args)
    if args.command == "retrospective":
        return generate_retrospective(args)
    if args.command == "submit":
        return submit_feedback(args)
    return export_feedback(args)


if __name__ == "__main__":
    sys.exit(main())
