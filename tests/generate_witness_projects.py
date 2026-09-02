#!/usr/bin/env python3
"""Generate reproducible clean and legacy witness projects under tests/fixtures/projects/."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    print("Missing dependency: PyYAML. Install requirements.txt first.", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES_DIR = ROOT / "tests" / "fixtures" / "projects"
CLEAN_DIR = FIXTURES_DIR / "clean"
LEGACY_DIR = FIXTURES_DIR / "legacy"
MANIFEST_PATH = FIXTURES_DIR / "witness-manifest.json"
DO_NOT_EDIT_CONTENT = """# Witness fixture — do not edit as framework product code

This directory is a **reproducible installed-project witness** for tests only.

To change framework behavior, edit `src/`, `adapters/`, etc. at the repository root,
then regenerate witnesses:

```bash
python tests/generate_witness_projects.py --write
```

See `tests/fixtures/projects/README.md`.
"""

PROJECT_OWNED_DIRS = (
    "work-units",
    "events",
    "evidence",
    "findings",
    "observations",
    "retrospectives",
    "decisions",
    "context-packages",
    "logs",
    "metrics",
    "acceptance",
    "releases",
    "audits",
    "migration-backups",
)

OBSOLETE_MANAGED_REL = ".cursor/skills/legacy-witness-removed/SKILL.md"
OBSOLETE_MANAGED_CONTENT = """\
---
name: legacy-witness-removed
description: Obsolete managed skill retained from an older framework install (witness fixture).
---
# Legacy witness removed skill

This file simulates a framework-managed artifact dropped from current managed_files.
It must remain on disk until a Distribution update classifies and archives it.
"""

WITNESS_V2_STAMP = {
    "revision": 1,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
}

WITNESS_INSTALL_STAMP = "2026-01-01T00:00:00+00:00"

IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".git"}
IGNORE_SUFFIXES = {".pyc", ".pyo"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Regenerate to a temp dir and compare hashes with witness-manifest.json",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write generated trees to tests/fixtures/projects/{clean,legacy}/",
    )
    return parser.parse_args()


def constitution_version() -> str:
    text = (ROOT / ".ai-team" / "constitution" / "constitution.yaml").read_text(
        encoding="utf-8"
    )
    match = re.search(r'(?m)^\s{2}version:\s*["\']?([^"\'\s]+)', text)
    if not match:
        raise RuntimeError("Could not read Constitution version from source tree")
    return match.group(1)


def framework_version() -> str:
    payload = json.loads((ROOT / ".ai-team" / "framework-version.json").read_text(encoding="utf-8"))
    return payload["version"]


def install_target(parent: Path, project_id: str, project_name: str) -> Path:
    target = parent / project_id
    if target.exists():
        shutil.rmtree(target)
    result = subprocess.run(
        [
            sys.executable,
            "tools/install.py",
            "--target",
            str(target),
            "--project-id",
            project_id,
            "--project-name",
            project_name,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "tools/install.py failed:\n" + result.stderr + result.stdout
        )
    return target


def clear_project_owned_runtime(target: Path) -> None:
    ai = target / ".ai-team"
    for dirname in PROJECT_OWNED_DIRS:
        path = ai / dirname
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            continue
        if dirname == "migration-backups":
            gitignore = path / ".gitignore"
            for child in path.iterdir():
                if child.name != ".gitignore":
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            if not gitignore.exists():
                gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")
            continue
        if path.is_dir():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    user_dir = ai / "user"
    if user_dir.exists():
        shutil.rmtree(user_dir)


def minimal_project_state(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "constitution_version": constitution_version(),
        "phase": "not_compiled",
        "gates": {
            "G0": {"status": "not_required"},
            "G1": {"status": "not_required"},
            "G2": {"status": "not_required"},
            "G3": {"status": "not_required"},
            "G4": {"status": "not_required"},
        },
        "work_units": {},
        "dependency_edges": [],
        "active_workers": [],
        "open_decisions": [],
        "open_blockers": [],
        "open_defects": [],
        "open_findings": [],
        "last_updated": "2026-01-01T00:00:00+00:00",
    }


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def normalize_installation_record(target: Path) -> None:
    record_path = target / ".ai-team" / "installation-record.json"
    if not record_path.is_file():
        return
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["installed_at"] = WITNESS_INSTALL_STAMP
    record["last_updated_at"] = WITNESS_INSTALL_STAMP
    record_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def finalize_clean_witness(target: Path, project_id: str) -> None:
    clear_project_owned_runtime(target)
    write_yaml(
        target / ".ai-team" / "state" / "project-state.yaml",
        minimal_project_state(project_id),
    )
    profile_path = target / ".ai-team" / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile.setdefault("setup_status", {})["note"] = (
        "Witness clean fixture — minimal post-install project data."
    )
    profile["setup_status"]["cursor_compile_opt_in"] = True
    write_yaml(profile_path, profile)
    normalize_installation_record(target)


def work_unit_base(wu_id: str, title: str, status: str) -> dict:
    return {
        "id": wu_id,
        "title": title,
        "objective": {
            "result": f"Witness legacy scenario for {wu_id}.",
            "rationale": "Document 13 Phase 0 witness project fixture.",
        },
        "scope": {"include": ["witness-scenario"], "exclude": []},
        "expected_behavior": "Static witness fixture for migration and distribution tests.",
        "applicable_rules_requirements": ["Document 13 §3 Phase 0"],
        "acceptance_criteria": ["Fixture validates and represents intended scenario."],
        "dependencies": [],
        "risk": {"class": "low", "reasons": ["Static fixture"]},
        "required_verification": {
            "unit_tests": False,
            "integration_tests": True,
            "contract_tests": False,
            "e2e": False,
            "qa": False,
            "review": False,
            "security_review": False,
            "audit": False,
            "human_acceptance": False,
        },
        "context_package_ref": None,
        "status": status,
        **WITNESS_V2_STAMP,
        "events": [],
        "evidence": [],
        "outcomes": {
            "review_status": "pending",
            "audit_status": "not_required",
            "critical_open_items": [],
            "defects": [],
            "audit_findings": [],
            "human_acceptance": None,
        },
    }


LEGACY_LAYOUT_VERSION = "0.6.0"


def downgrade_to_legacy_layout(target: Path) -> None:
    """Reconstruct what a pre-0.7.0 install looked like (Document 11 §4).

    The 0.7.0 layout migration moved `src/governed_ai` and `adapters/cursor`
    (framework-root trees, mirrored verbatim into every installed project)
    into `.ai-team/runtime/governed_ai`. `distribution/installer/migrate_layout.py`
    needs a fixture that still has the *old* layout to migrate from — so this
    reverses `install_target()`'s runtime-isolated output back to the old
    layout, using the framework's own relocation enumeration
    (`distribution.installer.source_files._iter_relocated_prefix_files`)
    rather than re-deriving the old path from the new one: the two old trees
    merge into one new-layout directory (`adapters/cursor/__init__.py` and
    `src/governed_ai/adapters/cursor/__init__.py` both land at
    `.ai-team/runtime/governed_ai/adapters/cursor/__init__.py`), which makes
    reversing the new path ambiguous. The enumerator instead hands back each
    live source file directly, so the old relative path is simply that file's
    path relative to the framework root — no reconstruction needed.
    """
    from distribution.installer.paths import RELOCATED_COPY_FILES
    from distribution.installer.source_files import _iter_relocated_prefix_files

    runtime_root = target / ".ai-team" / "runtime"
    if runtime_root.is_dir():
        shutil.rmtree(runtime_root)

    old_managed: set[str] = set()
    for item in ("src/governed_ai", "adapters/cursor"):
        for _new_relative, source in _iter_relocated_prefix_files(ROOT, item):
            old_relative = source.relative_to(ROOT).as_posix()
            destination = target / old_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            old_managed.add(old_relative)

    installed_requirements = target / ".ai-team" / "requirements.txt"
    if installed_requirements.is_file():
        installed_requirements.unlink()
    for src_file, _dest_file in RELOCATED_COPY_FILES:
        shutil.copy2(ROOT / src_file, target / src_file)
        old_managed.add(src_file)

    version_path = target / ".ai-team" / "framework-version.json"
    version_payload = json.loads(version_path.read_text(encoding="utf-8"))
    version_payload["version"] = LEGACY_LAYOUT_VERSION
    relocated_new_prefix = ".ai-team/runtime/"
    relocated_new_files = {dest for _src, dest in RELOCATED_COPY_FILES}
    kept = [
        rel
        for rel in version_payload["managed_files"]
        if not rel.startswith(relocated_new_prefix) and rel not in relocated_new_files
    ]
    version_payload["managed_files"] = sorted(set(kept) | old_managed)
    version_path.write_text(
        json.dumps(version_payload, indent=2) + "\n", encoding="utf-8"
    )


def apply_legacy_mutations(target: Path, project_id: str) -> None:
    ai = target / ".ai-team"
    finalize_clean_witness(target, project_id)
    downgrade_to_legacy_layout(target)

    # User modification — custom project-profile note and extension field.
    profile_path = ai / "project-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["setup_status"]["note"] = (
        "Witness legacy fixture — user customized setup note after install."
    )
    profile["extensions"] = {
        "witness": {
            "operator": "fixture-generator",
            "purpose": "Simulates user-edited project-owned profile metadata.",
        }
    }
    write_yaml(profile_path, profile)

    user_notes = ai / "user" / "local-notes.yaml"
    write_yaml(
        user_notes,
        {
            "created_by": "witness-operator",
            "note": "User-added project-owned file under .ai-team/user/ (not framework-managed).",
        },
    )

    wu_ready = work_unit_base("WU-WITNESS-READY", "Witness ready Work Unit", "ready")
    wu_active = work_unit_base(
        "WU-WITNESS-ACTIVE", "Witness active Work Unit", "in_progress"
    )
    wu_active["objective"]["rationale"] = (
        "USER EDIT — operator adjusted rationale after starting execution."
    )
    wu_active["context_package_ref"] = "CTX-WU-WITNESS-ACTIVE"
    wu_active["events"] = ["EVT-20260101-100000-orchestrator-start"]

    wu_done = work_unit_base("WU-WITNESS-DONE", "Witness completed Work Unit", "done")
    wu_done["events"] = [
        "EVT-20260101-100000-orchestrator-start",
        "EVT-20260101-110000-backend-handoff",
        "EVT-20260101-120000-wu-done",
    ]
    wu_done["evidence"] = [{"id": "EV-WITNESS-DONE-001", "type": "test_execution"}]
    wu_done["outcomes"]["review_status"] = "approved"
    wu_done["outcomes"]["human_acceptance"] = None

    for payload in (wu_ready, wu_active, wu_done):
        write_yaml(ai / "work-units" / f"{payload['id']}.yaml", payload)

    write_yaml(
        ai / "context-packages" / "CTX-WU-WITNESS-ACTIVE.yaml",
        {
            "id": "CTX-WU-WITNESS-ACTIVE",
            "work_unit": "WU-WITNESS-ACTIVE",
            "role": "backend-developer",
            "assembled_at": "2026-01-01T10:00:00+00:00",
            "items": [
                {
                    "level": "L3_work_unit",
                    "source": ".ai-team/work-units/WU-WITNESS-ACTIVE.yaml",
                    "provenance": "derived",
                    "reason": "Active witness Work Unit context",
                }
            ],
            "open_context_requests": [],
        },
    )

    write_yaml(
        ai / "events" / "EVT-20260101-100000-orchestrator-start.yaml",
        {
            "id": "EVT-20260101-100000-orchestrator-start",
            "type": "STATUS",
            "work_unit": "WU-WITNESS-ACTIVE",
            "created_at": "2026-01-01T10:00:00+00:00",
            "created_by_role": "orchestrator",
            "summary": "Orchestrator started WU-WITNESS-ACTIVE on witness legacy fixture.",
            "details": {"branch": "wu/WU-WITNESS-ACTIVE"},
            "affected_nodes": ["WU-WITNESS-ACTIVE"],
            "requires_human": False,
            "status": "open",
        },
    )
    write_yaml(
        ai / "events" / "EVT-20260101-110000-backend-handoff.yaml",
        {
            "id": "EVT-20260101-110000-backend-handoff",
            "type": "HANDOFF",
            "work_unit": "WU-WITNESS-ACTIVE",
            "created_at": "2026-01-01T11:00:00+00:00",
            "created_by_role": "backend-developer",
            "summary": "Backend handoff for witness active Work Unit.",
            "details": {"commit_sha": "0000000000000000000000000000000000000000"},
            "affected_nodes": ["WU-WITNESS-ACTIVE"],
            "requires_human": False,
            "status": "open",
        },
    )
    write_yaml(
        ai / "events" / "EVT-20260101-120000-wu-done.yaml",
        {
            "id": "EVT-20260101-120000-wu-done",
            "type": "STATUS",
            "work_unit": "WU-WITNESS-DONE",
            "created_at": "2026-01-01T12:00:00+00:00",
            "created_by_role": "orchestrator",
            "summary": "Witness done Work Unit marked complete.",
            "details": {},
            "affected_nodes": ["WU-WITNESS-DONE"],
            "requires_human": False,
            "status": "open",
        },
    )

    write_yaml(
        ai / "evidence" / "EV-WITNESS-DONE-001.yaml",
        {
            "id": "EV-WITNESS-DONE-001",
            "work_unit": "WU-WITNESS-DONE",
            "type": "test_execution",
            "code_revision": "0000000000000000000000000000000000000000",
            "performed_at": "2026-01-01T11:30:00+00:00",
            "performed_by_role": "qa-test",
            "command_or_observation": "python -m pytest tests/test_witness_projects.py -q",
            "result": {"status": "passed", "details": {"tests": "witness fixture smoke"}},
            "demonstrates": ["Witness legacy Work Unit verification path"],
            "limitations": ["Fixture-only evidence — no live runtime"],
            "artifacts": [],
        },
    )

    write_yaml(
        ai / "observations" / "OBS-WITNESS-001.yaml",
        {
            "id": "OBS-WITNESS-001",
            "recorded_at": "2026-01-01T09:00:00+00:00",
            "recorded_by": "witness-operator",
            "project_id": project_id,
            "framework_version": framework_version(),
            "constitution_version": constitution_version(),
            "work_unit": "WU-WITNESS-ACTIVE",
            "phase": "execution",
            "category": "tooling",
            "severity": "low",
            "symptom": "Witness legacy observation for migration baseline.",
            "classification": {"origin": "framework", "confidence": "confirmed"},
            "impact": {
                "blocked_minutes": 0,
                "rework_required": False,
                "human_intervention": False,
                "affected_work_units": [],
            },
            "evidence_refs": [],
            "workaround": None,
            "candidate_improvement": None,
            "recurrence_key": None,
            "status": "open",
            "resolution": None,
        },
    )

    write_yaml(
        ai / "retrospectives" / "RET-WITNESS-001.yaml",
        {
            "id": "RET-WITNESS-001",
            "generated_at": "2026-01-01T13:00:00+00:00",
            "project_id": project_id,
            "framework_version": framework_version(),
            "constitution_version": constitution_version(),
            "scope": {"type": "work_unit", "ref": "WU-WITNESS-DONE"},
            "source_snapshot": {
                "observations": 1,
                "events": 3,
                "decisions": 2,
                "findings": 1,
                "acceptances": 0,
                "work_units": 3,
            },
            "observation_summary": {
                "total": 1,
                "open": 1,
                "by_category": {"tooling": 1},
                "by_origin": {"framework": 1},
                "by_severity": {"low": 1},
            },
            "signals": {
                "blocked_minutes": 0,
                "rework_observations": 0,
                "human_interventions": 0,
                "event_types": {"STATUS": 2, "HANDOFF": 1},
                "work_unit_statuses": {"ready": 1, "in_progress": 1, "done": 1},
            },
            "observation_refs": ["OBS-WITNESS-001"],
            "unresolved_observation_refs": ["OBS-WITNESS-001"],
            "notes": "Witness legacy retrospective — sanitized representative example.",
            "status": "generated",
        },
    )

    write_yaml(
        ai / "decisions" / "gate-g1-20260101-witness.yaml",
        {
            "id": "G1-WITNESS-0001",
            "gate": "G1",
            "status": "approved",
            "by": "witness-operator",
            "at": "2026-01-01T08:00:00+00:00",
            "note": "Witness legacy G1 approval for execution plan.",
        },
    )
    write_yaml(
        ai / "decisions" / "DEC-WITNESS-001.yaml",
        {
            "id": "DEC-WITNESS-001",
            "question": "Should the witness legacy fixture keep the obsolete managed skill file?",
            "why_human_authority_is_required": "Product policy on archiving obsolete managed artifacts.",
            "options": [
                {"id": "keep", "label": "Keep until Distribution update"},
                {"id": "archive", "label": "Archive during next update"},
            ],
            "status": "pending_human",
            **WITNESS_V2_STAMP,
        },
    )

    write_yaml(
        ai / "findings" / "FIND-WITNESS-001.yaml",
        {
            "id": "FIND-WITNESS-001",
            "severity": "low",
            "classification": "expected_and_observed",
            "claim": "Obsolete managed file remains on disk until update classifies it.",
            "evidence": ["OBS-WITNESS-001"],
            "limitations": ["Static fixture — no live update executed"],
            "remediation_required": False,
            "status": "open",
            **WITNESS_V2_STAMP,
        },
    )

    legacy_state = {
        "project_id": project_id,
        "constitution_version": constitution_version(),
        "phase": "execution",
        "gates": {
            "G0": {
                "status": "passed",
                "evaluated_at": "2026-01-01T00:00:00+00:00",
                "note": "Witness legacy readiness snapshot.",
            },
            "G1": {
                "status": "approved",
                "by": "witness-operator",
                "at": "2026-01-01T08:00:00+00:00",
                "note": "Witness legacy execution plan approved.",
            },
            "G2": {"status": "not_required"},
            "G3": {"status": "not_required"},
            "G4": {"status": "not_required"},
        },
        "milestones": [
            {
                "id": "M-WITNESS",
                "title": "Witness legacy milestone",
                "work_units": [
                    "WU-WITNESS-READY",
                    "WU-WITNESS-ACTIVE",
                    "WU-WITNESS-DONE",
                ],
            }
        ],
        "work_units": {
            "WU-WITNESS-READY": {
                "status": "ready",
                "milestone": "M-WITNESS",
                "risk": "low",
            },
            "WU-WITNESS-ACTIVE": {
                "status": "in_progress",
                "milestone": "M-WITNESS",
                "risk": "medium",
            },
            "WU-WITNESS-DONE": {
                "status": "done",
                "milestone": "M-WITNESS",
                "risk": "low",
                "done_event": "EVT-20260101-120000-wu-done",
                "evidence": ["EV-WITNESS-DONE-001"],
            },
        },
        "dependency_edges": [
            {"from": "WU-WITNESS-ACTIVE", "to": "WU-WITNESS-READY", "type": "blocks"},
            {"from": "WU-WITNESS-DONE", "to": "WU-WITNESS-ACTIVE", "type": "blocks"},
        ],
        "active_workers": [],
        "open_decisions": ["DEC-WITNESS-001"],
        "open_blockers": [],
        "open_defects": [],
        "open_findings": ["FIND-WITNESS-001"],
        "last_updated": "2026-01-01T13:00:00+00:00",
    }
    write_yaml(ai / "state" / "project-state.yaml", legacy_state)

    # Obsolete managed file — listed in manifest but absent from current source managed_files.
    obsolete_path = target / OBSOLETE_MANAGED_REL
    obsolete_path.parent.mkdir(parents=True, exist_ok=True)
    obsolete_path.write_text(OBSOLETE_MANAGED_CONTENT, encoding="utf-8")
    version_path = ai / "framework-version.json"
    version_payload = json.loads(version_path.read_text(encoding="utf-8"))
    managed = list(version_payload.get("managed_files") or [])
    if OBSOLETE_MANAGED_REL not in managed:
        managed.append(OBSOLETE_MANAGED_REL)
        managed.sort()
        version_payload["managed_files"] = managed
        version_path.write_text(json.dumps(version_payload, indent=2) + "\n", encoding="utf-8")
    normalize_installation_record(target)


def should_skip(path: Path) -> bool:
    return (
        any(part in IGNORE_NAMES for part in path.parts)
        or path.suffix in IGNORE_SUFFIXES
    )


def iter_fixture_files(root: Path) -> list[Path]:
    files = [p for p in root.rglob("*") if p.is_file() and not should_skip(p)]
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def normalize_text_files(root: Path) -> None:
    """Store generated UTF-8 fixtures with LF on every operating system."""
    for path in iter_fixture_files(root):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        if canonical != raw:
            path.write_bytes(canonical)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def build_tree_manifest(name: str, root: Path) -> dict:
    entries = []
    for path in iter_fixture_files(root):
        rel = path.relative_to(root).as_posix()
        entries.append({"path": rel, "sha256": sha256_file(path)})
    return {"name": name, "root": name, "file_count": len(entries), "files": entries}


def copy_fixture_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = set(IGNORE_NAMES)
        for name in names:
            if any(name.endswith(suffix) for suffix in IGNORE_SUFFIXES):
                ignored.add(name)
        return ignored

    for child in source.iterdir():
        dest = destination / child.name
        if child.is_dir():
            shutil.copytree(child, dest, ignore=ignore)
        else:
            shutil.copy2(child, dest)


def write_do_not_edit_marker(destination: Path) -> None:
    (destination / "DO_NOT_EDIT_AS_PRODUCT.md").write_text(
        DO_NOT_EDIT_CONTENT, encoding="utf-8"
    )


def write_manifest(clean_root: Path, legacy_root: Path) -> dict:
    manifest = {
        "framework_version": framework_version(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "platform": sys.platform,
        "description": "Reproducible witness projects for migration and distribution tests (Document 13 §3, Document 14 §2).",
        "scenarios": {
            "clean": {
                "summary": "Fresh install with minimal project-owned data.",
                "project_id": "witness-clean",
            },
            "legacy": {
                "summary": "Runtime artifacts, obsolete managed file, and user edits.",
                "project_id": "witness-legacy",
                "artifacts": {
                    "runtime_data": [
                        "work-units in ready/in_progress/done states",
                        "events, evidence, observations, retrospectives",
                        "gate decision and pending decision request",
                        "finding linked to obsolete managed file scenario",
                    ],
                    "obsolete_managed_files": [OBSOLETE_MANAGED_REL],
                    "user_modifications": [
                        "project-profile extensions + customized setup note",
                        "WU-WITNESS-ACTIVE user-edited rationale",
                        ".ai-team/user/local-notes.yaml",
                    ],
                },
            },
        },
        "trees": [
            build_tree_manifest("clean", clean_root),
            build_tree_manifest("legacy", legacy_root),
        ],
    }
    return manifest


def compare_manifests(expected: dict, actual: dict) -> list[str]:
    errors: list[str] = []
    expected_trees = {tree["name"]: tree for tree in expected.get("trees", [])}
    actual_trees = {tree["name"]: tree for tree in actual.get("trees", [])}
    for name in ("clean", "legacy"):
        if name not in actual_trees:
            errors.append(f"Missing regenerated tree: {name}")
            continue
        exp_files = {entry["path"]: entry["sha256"] for entry in expected_trees[name]["files"]}
        act_files = {entry["path"]: entry["sha256"] for entry in actual_trees[name]["files"]}
        if exp_files.keys() != act_files.keys():
            missing = sorted(set(exp_files) - set(act_files))
            extra = sorted(set(act_files) - set(exp_files))
            if missing:
                errors.append(f"{name}: missing paths after regeneration: {missing[:5]}")
            if extra:
                errors.append(f"{name}: unexpected paths after regeneration: {extra[:5]}")
        for path, digest in exp_files.items():
            if act_files.get(path) != digest:
                errors.append(f"{name}: hash mismatch for {path}")
    return errors


def generate_trees(parent: Path) -> tuple[Path, Path]:
    clean = install_target(parent, "witness-clean", "Witness Clean")
    finalize_clean_witness(clean, "witness-clean")

    legacy = install_target(parent, "witness-legacy", "Witness Legacy")
    apply_legacy_mutations(legacy, "witness-legacy")
    normalize_text_files(clean)
    normalize_text_files(legacy)
    write_do_not_edit_marker(clean)
    write_do_not_edit_marker(legacy)
    normalize_text_files(clean)
    normalize_text_files(legacy)
    return clean, legacy


def main() -> int:
    args = parse_args()
    if not args.verify and not args.write:
        print("Specify --write and/or --verify", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="witness-gen-") as temp_dir:
        temp_parent = Path(temp_dir)
        clean_root, legacy_root = generate_trees(temp_parent)
        manifest = write_manifest(clean_root, legacy_root)

        if args.write:
            FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
            copy_fixture_tree(clean_root, CLEAN_DIR)
            copy_fixture_tree(legacy_root, LEGACY_DIR)
            MANIFEST_PATH.write_bytes(
                (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            )
            print(f"Wrote {CLEAN_DIR}")
            print(f"Wrote {LEGACY_DIR}")
            print(f"Wrote {MANIFEST_PATH}")

        if args.verify:
            if not MANIFEST_PATH.exists():
                print(f"Missing manifest for verify: {MANIFEST_PATH}", file=sys.stderr)
                return 2
            expected = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            errors = compare_manifests(expected, manifest)
            if errors:
                print("Witness manifest verification failed:", file=sys.stderr)
                for error in errors:
                    print(f"  - {error}", file=sys.stderr)
                return 1
            print("Witness manifest verification: PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
