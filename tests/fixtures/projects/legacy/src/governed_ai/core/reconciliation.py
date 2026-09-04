"""Brownfield baseline reconciliation and compile fencing.

The reconciliation report is project-owned evidence.  Repository content is
observed reality, never product authority; the report links observations back
to human sources before a project can be compiled.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

REPORT_RELATIVE_PATH = Path(".ai-team/reconciliation/baseline.yaml")
INSTALLATION_RECORD = Path(".ai-team/installation-record.json")
REQUIRED_HUMAN_MATERIAL = (
    "objectives",
    "users",
    "business_rules",
    "constraints",
    "out_of_scope",
    "prior_decisions",
    "acceptance_criteria",
)
MATERIAL_READY_STATUSES = frozenset({"sufficient", "not_applicable"})
TERMINAL_RESOLUTION_STATUSES = frozenset({"completed", "waived"})
DESTRUCTIVE_ACTIONS = frozenset({"migrate", "rewrite", "isolate", "delete"})

_IGNORED_PARTS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
    }
)
_IGNORED_ROOTS = frozenset({"build", "dist"})
_CODE_ROOTS = (
    "src",
    "app",
    "apps",
    "lib",
    "packages",
    "services",
    "backend",
    "frontend",
)
_ROOT_CODE_SUFFIXES = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".cs", ".php", ".rb"}
)


@dataclass(frozen=True)
class ProjectFingerprint:
    algorithm: str
    digest: str
    file_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "digest": self.digest,
            "file_count": self.file_count,
        }


def load_report(root: Path) -> dict[str, Any]:
    path = root / REPORT_RELATIVE_PATH
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{REPORT_RELATIVE_PATH.as_posix()} root must be an object")
    return payload


def _managed_paths(root: Path) -> set[str]:
    """Read managed paths without depending on installer-only modules."""
    path = root / INSTALLATION_RECORD
    if not path.is_file():
        return set()
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()

    paths: set[str] = set()
    sections: list[Any] = [
        (record.get("core") or {}).get("managed_files"),
        (record.get("distribution") or {}).get("managed_files"),
    ]
    for adapter in record.get("adapters") or []:
        if isinstance(adapter, dict):
            sections.append(adapter.get("managed_files"))
    if record.get("schema_version") == 1:
        sections.append(record.get("managed_files"))
    for entries in sections:
        for entry in entries or []:
            raw = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(raw, str):
                paths.add(raw.replace("\\", "/").removeprefix("./"))
    return paths


def _ignored(relative: Path, managed: set[str]) -> bool:
    posix = relative.as_posix()
    if posix == REPORT_RELATIVE_PATH.as_posix() or posix.startswith(
        REPORT_RELATIVE_PATH.parent.as_posix() + "/"
    ):
        return True
    if posix in managed:
        return True
    if relative.parts and relative.parts[0] in _IGNORED_ROOTS:
        return True
    if any(part in _IGNORED_PARTS for part in relative.parts):
        return True
    if relative.suffix in {".pyc", ".pyo"}:
        return True
    return False


def iter_project_owned_files(root: Path) -> Iterable[Path]:
    managed = _managed_paths(root)
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if not _ignored(relative, managed):
            yield path


def fingerprint_project(root: Path) -> ProjectFingerprint:
    digest = hashlib.sha256()
    count = 0
    for path in iter_project_owned_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        count += 1
    return ProjectFingerprint("sha256", f"sha256:{digest.hexdigest()}", count)


def has_application_code(root: Path) -> bool:
    for name in _CODE_ROOTS:
        candidate = root / name
        if candidate.is_dir() and any(
            path.is_file() and path.suffix.lower() in _ROOT_CODE_SUFFIXES
            for path in candidate.rglob("*")
        ):
            return True
    return any(
        path.is_file() and path.suffix.lower() in _ROOT_CODE_SUFFIXES
        for path in root.iterdir()
    )


def discover_inventory(root: Path) -> list[dict[str, str]]:
    """Return a bounded structural inventory for the skill to enrich semantically."""
    entries: list[dict[str, str]] = []
    candidates = {
        "src": "code",
        "app": "code",
        "apps": "code",
        "lib": "code",
        "packages": "code",
        "services": "code",
        "backend": "code",
        "frontend": "code",
        "tests": "test",
        "docs": "documentation",
        "migrations": "data",
        "infra": "infrastructure",
    }
    for name, kind in candidates.items():
        path = root / name
        if not path.exists():
            continue
        count = sum(1 for item in path.rglob("*") if item.is_file()) if path.is_dir() else 1
        entries.append(
            {
                "path": name,
                "kind": kind,
                "evidence": f"Detected {count} file(s); semantic review required.",
            }
        )
    for name in (
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "pom.xml",
        "go.mod",
        "Cargo.toml",
        "Dockerfile",
        "docker-compose.yml",
    ):
        if (root / name).is_file():
            entries.append(
                {"path": name, "kind": "dependency", "evidence": "Detected project file."}
            )
    return entries


def _authoritative_source_ids(root: Path) -> tuple[set[str], list[str]]:
    registry_path = root / ".ai-team" / "sources" / "source-registry.yaml"
    if not registry_path.is_file():
        return set(), ["authoritative source registry is missing"]
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return set(), [f"cannot read authoritative source registry: {exc}"]

    source_ids: set[str] = set()
    issues: list[str] = []
    for source in registry.get("sources") or []:
        if not isinstance(source, dict):
            continue
        if source.get("status") != "active" or source.get("authority") != "human":
            continue
        if source.get("type") not in {
            "human_construction_material",
            "recorded_human_decision",
        }:
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            continue
        path = source.get("path")
        if isinstance(path, str) and not (root / path).is_file():
            issues.append(f"active authoritative source {source_id!r} path does not exist: {path}")
            continue
        source_ids.add(source_id)
    return source_ids, issues


def _project_id_from_profile(root: Path) -> str | None:
    path = root / ".ai-team" / "project-profile.yaml"
    if not path.is_file():
        return None
    try:
        profile = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    project_id = (profile.get("project") or {}).get("id") or profile.get("project_id")
    return str(project_id) if project_id else None


def new_report(project_id: str, root: Path, generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_id": project_id,
        "status": "draft",
        "scope": {"include": ["."], "exclude": []},
        "human_material": {
            key: {"status": "missing", "source_refs": [], "note": ""}
            for key in REQUIRED_HUMAN_MATERIAL
        },
        "inventory": {
            "generated_at": generated_at,
            "entries": discover_inventory(root),
        },
        "convergence": [],
        "decisions": [],
        "verification": {"commands": [], "blocking_conflicts": 0},
        "baseline": None,
    }


def semantic_issues(
    report: dict[str, Any],
    *,
    root: Path | None = None,
    require_ready: bool = False,
    verify_fingerprint: bool = False,
) -> list[str]:
    issues: list[str] = []
    status = report.get("status")
    if require_ready and status != "ready":
        issues.append(f"reconciliation status must be 'ready' (found {status!r})")

    scope = report.get("scope") or {}
    if not scope.get("include"):
        issues.append("scope.include must identify at least one reconciled surface")

    material = report.get("human_material") or {}
    authoritative_source_ids: set[str] | None = None
    if root is not None:
        expected_project_id = _project_id_from_profile(root)
        if expected_project_id is not None and report.get("project_id") != expected_project_id:
            issues.append(
                "reconciliation project_id does not match project-profile.yaml "
                f"({report.get('project_id')!r} != {expected_project_id!r})"
            )
        authoritative_source_ids, source_issues = _authoritative_source_ids(root)
        issues.extend(source_issues)
    for key in REQUIRED_HUMAN_MATERIAL:
        entry = material.get(key) or {}
        entry_status = entry.get("status")
        if entry_status not in MATERIAL_READY_STATUSES:
            issues.append(f"human_material.{key} is not sufficient ({entry_status!r})")
        if entry_status in MATERIAL_READY_STATUSES and not entry.get("source_refs"):
            issues.append(f"human_material.{key} needs at least one authoritative source_ref")
        if entry_status == "not_applicable" and not str(entry.get("note") or "").strip():
            issues.append(f"human_material.{key} marked not_applicable needs an explanation")
        if entry_status in MATERIAL_READY_STATUSES and authoritative_source_ids is not None:
            unknown_refs = sorted(set(entry.get("source_refs") or []) - authoritative_source_ids)
            if unknown_refs:
                issues.append(
                    f"human_material.{key} references inactive, missing, or non-human sources: "
                    + ", ".join(unknown_refs)
                )

    if root is not None and has_application_code(root):
        entries = (report.get("inventory") or {}).get("entries") or []
        if not entries:
            issues.append("brownfield application code requires a non-empty as-built inventory")

    open_decisions = [
        item.get("id", "<unknown>")
        for item in report.get("decisions") or []
        if item.get("status") != "resolved"
    ]
    if open_decisions:
        issues.append("unresolved reconciliation decisions: " + ", ".join(open_decisions))
    for decision in report.get("decisions") or []:
        if decision.get("status") == "resolved" and not decision.get("resolution_ref"):
            issues.append(
                f"resolved decision {decision.get('id', '<unknown>')} needs resolution_ref"
            )

    inventory_entries = (report.get("inventory") or {}).get("entries") or []
    convergence_items = report.get("convergence") or []
    convergence_subjects = {
        str(item.get("subject")) for item in convergence_items if item.get("subject")
    }
    for entry in inventory_entries:
        path = entry.get("path", "<unknown>")
        if path not in convergence_subjects:
            issues.append(f"inventory surface {path!r} needs a convergence classification")

    blocking_conflicts = 0
    for item in convergence_items:
        item_id = item.get("id", "<unknown>")
        resolution_status = item.get("resolution_status")
        if resolution_status not in TERMINAL_RESOLUTION_STATUSES:
            blocking_conflicts += 1
            issues.append(f"convergence item {item_id} is not completed or waived")
        action = item.get("action")
        intent_refs = item.get("intent_refs") or []
        if not intent_refs:
            issues.append(f"convergence item {item_id} needs at least one intent_ref")
        if authoritative_source_ids is not None:
            unknown_intent_refs = sorted(set(intent_refs) - authoritative_source_ids)
            if unknown_intent_refs:
                issues.append(
                    f"convergence item {item_id} references inactive, missing, or non-human "
                    "intent sources: " + ", ".join(unknown_intent_refs)
                )
        needs_human_ref = (
            action in DESTRUCTIVE_ACTIONS
            or resolution_status == "waived"
            or item.get("classification") in {"conflicting", "undetermined"}
        )
        if (
            needs_human_ref
            and resolution_status in TERMINAL_RESOLUTION_STATUSES
            and not item.get("human_approval_ref")
        ):
            issues.append(
                f"convergence item {item_id} action {action!r} requires human_approval_ref"
            )

    declared_blocking = (report.get("verification") or {}).get("blocking_conflicts")
    if declared_blocking != blocking_conflicts:
        issues.append(
            "verification.blocking_conflicts does not match unresolved convergence items "
            f"(declared {declared_blocking!r}, observed {blocking_conflicts})"
        )

    commands = (report.get("verification") or {}).get("commands") or []
    if not commands:
        issues.append("verification.commands must contain verification evidence")
    for command in commands:
        if command.get("status") not in {"pass", "not_applicable"}:
            issues.append(
                f"verification command {command.get('command', '<unknown>')!r} did not pass"
            )

    baseline = report.get("baseline")
    if require_ready and not isinstance(baseline, dict):
        issues.append("ready reconciliation needs a baseline fingerprint")
    if verify_fingerprint and isinstance(baseline, dict) and root is not None:
        observed = fingerprint_project(root)
        if baseline.get("algorithm") != observed.algorithm:
            issues.append("baseline fingerprint algorithm is unsupported or changed")
        if baseline.get("digest") != observed.digest:
            issues.append("reconciliation baseline is stale: project-owned content changed")
        if baseline.get("file_count") != observed.file_count:
            issues.append("reconciliation baseline is stale: project-owned file count changed")
    return issues


__all__ = [
    "DESTRUCTIVE_ACTIONS",
    "ProjectFingerprint",
    "REPORT_RELATIVE_PATH",
    "discover_inventory",
    "fingerprint_project",
    "has_application_code",
    "iter_project_owned_files",
    "load_report",
    "new_report",
    "semantic_issues",
]
