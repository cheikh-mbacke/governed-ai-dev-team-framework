#!/usr/bin/env python3
"""Create, finalize, and verify the pre-compile reconciliation baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(ROOT)

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.reconciliation import (
    REPORT_RELATIVE_PATH,
    fingerprint_project,
    load_report,
    new_report,
    semantic_issues,
)
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed

SCHEMA_PATH = ROOT / ".ai-team" / "schemas" / "reconciliation.schema.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(payload["summary"])
    for issue in payload.get("issues") or []:
        print(f"- {issue}")


def _project_id() -> str:
    profile_path = ROOT / ".ai-team" / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    return str((profile.get("project") or {}).get("id") or profile.get("project_id") or "project")


def _write_report(report: dict) -> Path:
    path = ROOT / REPORT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(report, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def _schema_issues(report: dict) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(report), key=lambda e: list(e.path))
    return [
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors
    ]


def init_report(force: bool, as_json: bool) -> int:
    path = ROOT / REPORT_RELATIVE_PATH
    if path.exists() and not force:
        _emit(
            {
                "status": "exists",
                "summary": f"Reconciliation report already exists: {REPORT_RELATIVE_PATH.as_posix()}",
                "issues": ["Use --force only to intentionally replace the draft."],
            },
            as_json=as_json,
        )
        return 2
    report = new_report(_project_id(), ROOT, _now())
    _write_report(report)
    _emit(
        {
            "status": "draft",
            "summary": f"Created reconciliation draft: {REPORT_RELATIVE_PATH.as_posix()}",
            "inventory_entries": len(report["inventory"]["entries"]),
            "issues": [],
        },
        as_json=as_json,
    )
    return 0


def finalize_report(as_json: bool) -> int:
    try:
        report = load_report(ROOT)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        _emit(
            {"status": "blocked", "summary": "Cannot load reconciliation report.", "issues": [str(exc)]},
            as_json=as_json,
        )
        return 2
    issues = _schema_issues(report)
    if report.get("status") not in {"approved", "applying"}:
        issues.append("status must be 'approved' or 'applying' before finalization")
    issues.extend(semantic_issues(report, root=ROOT))
    if issues:
        _emit(
            {"status": "blocked", "summary": "Reconciliation cannot be finalized.", "issues": issues},
            as_json=as_json,
        )
        return 1

    fingerprint = fingerprint_project(ROOT)
    report["status"] = "ready"
    report["baseline"] = {**fingerprint.as_dict(), "verified_at": _now()}
    _write_report(report)
    _emit(
        {
            "status": "ready",
            "summary": "Reconciliation baseline is ready for /compile-project.",
            "baseline": report["baseline"],
            "issues": [],
        },
        as_json=as_json,
    )
    return 0


def check_report(as_json: bool) -> int:
    path = ROOT / REPORT_RELATIVE_PATH
    if not path.is_file():
        _emit(
            {
                "status": "missing",
                "summary": "Reconciliation required before /compile-project.",
                "issues": ["Run /reconcile-project first."],
            },
            as_json=as_json,
        )
        return 1
    try:
        report = load_report(ROOT)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        _emit(
            {"status": "invalid", "summary": "Invalid reconciliation report.", "issues": [str(exc)]},
            as_json=as_json,
        )
        return 1
    issues = _schema_issues(report)
    issues.extend(
        semantic_issues(report, root=ROOT, require_ready=True, verify_fingerprint=True)
    )
    payload = {
        "status": "ready" if not issues else "blocked",
        "summary": (
            "Reconciliation baseline is current; /compile-project may proceed."
            if not issues
            else "Reconciliation baseline does not permit /compile-project."
        ),
        "issues": issues,
    }
    _emit(payload, as_json=as_json)
    return 0 if not issues else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="create a draft with structural inventory")
    init_parser.add_argument("--force", action="store_true", help="replace an existing draft")
    subparsers.add_parser("finalize", help="validate and fingerprint an approved reconciliation")
    subparsers.add_parser("check", help="enforce the reconciliation fence before compile")
    args = parser.parse_args()

    try:
        ensure_client_cycle_allowed(Workspace.from_root(ROOT))
    except GatewayError as exc:
        print(exc.message)
        return exit_code_for(exc.code)

    if args.command == "init":
        return init_report(args.force, args.json)
    if args.command == "finalize":
        return finalize_report(args.json)
    return check_report(args.json)


if __name__ == "__main__":
    raise SystemExit(main())
