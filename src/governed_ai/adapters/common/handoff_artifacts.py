"""Defensive cleanup of agent handoff artifacts before the execution gateway.

Agents sometimes declare compiler packages, host temporary logs, or more
files than the gateway accepts. Those declarations are dropped or relocated
here so a finished Work Unit is not rejected after the product change already
exists. The rules do not name a language or a framework.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from governed_ai.core.execution_gateway.contracts import MAX_ARTIFACT_BYTES, MAX_ARTIFACTS
from governed_ai.core.execution_gateway.evidence import is_host_absolute_path, sha256_file
from governed_ai.core.orchestrator.boundary import (
    is_build_output_path,
    is_packaged_binary_path,
)


def _safe_name(path: str) -> str:
    name = Path(path.replace("\\", "/")).name
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name).strip(".-")
    if not cleaned:
        cleaned = "evidence.txt"
    if cleaned.endswith(".log"):
        cleaned = f"{cleaned[:-4]}.txt"
    return cleaned


def _relocate_host_file(project_root: Path, evidence_dir: Path, source: Path) -> str | None:
    if not source.is_file():
        return None
    try:
        size = source.stat().st_size
    except OSError:
        return None
    if size > MAX_ARTIFACT_BYTES:
        return None
    evidence_dir.mkdir(parents=True, exist_ok=True)
    destination = evidence_dir / _safe_name(source.name)
    if destination.resolve() != source.resolve():
        shutil.copy2(source, destination)
    try:
        relative = destination.resolve().relative_to(project_root.resolve())
    except ValueError:
        return None
    return relative.as_posix()


def sanitize_handoff(
    project_root: Path,
    work_unit_id: str,
    *,
    artifacts: list[Any],
    checks: list[Any],
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Return artifacts and checks the gateway can accept."""
    root = project_root.resolve()
    evidence_dir = root / ".ai-team" / "evidence" / (work_unit_id or "_unscoped")
    path_map: dict[str, str] = {}
    kept: list[dict[str, Any]] = []
    for raw in artifacts:
        if not isinstance(raw, dict):
            continue
        declared = str(raw.get("path") or "").strip()
        if (
            not declared
            or is_build_output_path(declared)
            or is_packaged_binary_path(declared)
        ):
            continue
        relocated: str | None = None
        if is_host_absolute_path(declared):
            relocated = _relocate_host_file(root, evidence_dir, Path(declared))
            if relocated is None:
                continue
            path_map[declared] = relocated
        else:
            relative = declared.replace("\\", "/")
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if not candidate.is_file():
                continue
            try:
                size = candidate.stat().st_size
            except OSError:
                continue
            if size > MAX_ARTIFACT_BYTES:
                continue
            if relative.endswith(".log") and "/.ai-team/evidence/" in f"/{relative}":
                renamed = candidate.with_suffix(".txt")
                if renamed != candidate:
                    renamed.parent.mkdir(parents=True, exist_ok=True)
                    candidate.replace(renamed)
                    relocated = renamed.resolve().relative_to(root).as_posix()
                    path_map[declared] = relocated
            else:
                relocated = relative
        if relocated is None:
            continue
        updated = dict(raw)
        updated["path"] = relocated
        if relocated != declared.replace("\\", "/"):
            try:
                digest = sha256_file(root / relocated)
            except OSError:
                continue
            # The gateway prefers agent_reported_sha256 over sha256. Both must
            # describe the file actually submitted after a relocate or rename.
            updated["sha256"] = digest
            updated["agent_reported_sha256"] = digest
        kept.append(updated)
        if len(kept) >= MAX_ARTIFACTS:
            break

    rewritten_checks: list[Any] = []
    for check in checks:
        if not isinstance(check, dict):
            rewritten_checks.append(check)
            continue
        ref = check.get("evidence_ref")
        if isinstance(ref, str) and ref in path_map:
            copied = dict(check)
            copied["evidence_ref"] = path_map[ref]
            rewritten_checks.append(copied)
        else:
            rewritten_checks.append(check)
    return kept, rewritten_checks
