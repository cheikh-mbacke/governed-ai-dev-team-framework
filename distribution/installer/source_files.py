"""Managed source file enumeration and copy planning."""

from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path

from distribution.installer.constants import COPY_ITEMS, LEGACY_VERSION_REL, PROJECT_OWNED_PATTERNS
from distribution.installer.record import INSTALLATION_RECORD_FILE, LEGACY_VERSION_FILE, normalize_path


def bootstrap_adapter_imports(source_root: Path) -> None:
    root = str(source_root)
    src = str(source_root / "src")
    for entry in (root, src):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def is_project_owned(rel_posix: str) -> bool:
    if rel_posix == ".ai-team/migration-backups/.gitignore":
        return False
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in PROJECT_OWNED_PATTERNS)


def is_docs_product_readme(rel_posix: str) -> bool:
    return rel_posix == "docs/product/README.md" or (
        rel_posix.startswith("docs/product/")
        and rel_posix.endswith("/README.md")
        and rel_posix.count("/") == 3
    )


def compile_profile_for_target(source_root: Path, target: Path, project_id: str | None = None) -> dict:
    bootstrap_adapter_imports(source_root)
    from adapters.cursor.compiler.install_support import (
        load_project_profile_yaml,
        minimal_project_profile,
    )

    profile_path = target / ".ai-team" / "project-profile.yaml"
    if profile_path.is_file():
        return load_project_profile_yaml(profile_path)
    if project_id:
        return minimal_project_profile(project_id=project_id)
    return minimal_project_profile()


def iter_managed_source_files(
    source_root: Path,
    target: Path | None = None,
    project_id: str | None = None,
    *,
    compile_cursor: bool = True,
):
    profile = (
        compile_profile_for_target(source_root, target, project_id=project_id)
        if target and compile_cursor
        else None
    )
    for item in COPY_ITEMS:
        if item == ".cursor":
            if not compile_cursor:
                if target is None:
                    continue
                cursor_root = target / ".cursor"
                if not cursor_root.is_dir():
                    continue
                for path in sorted(cursor_root.rglob("*")):
                    if path.is_file():
                        relative = path.relative_to(target)
                        yield relative, path
                continue
            bootstrap_adapter_imports(source_root)
            from adapters.cursor.compiler.install_support import iter_compiled_cursor_files

            for relative, path in iter_compiled_cursor_files(source_root, profile):
                rel_posix = relative.as_posix()
                if is_project_owned(rel_posix):
                    continue
                yield relative, path
            continue
        src = source_root / item
        if not src.exists():
            continue
        paths = src.rglob("*") if src.is_dir() else [src]
        for path in paths:
            if path.is_dir():
                continue
            relative = path.relative_to(source_root)
            rel_posix = relative.as_posix()
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            if ".transactions" in relative.parts:
                continue
            if relative == LEGACY_VERSION_FILE:
                continue
            if relative.as_posix() == INSTALLATION_RECORD_FILE.as_posix():
                continue
            if item == "docs/product" and not is_docs_product_readme(rel_posix):
                continue
            if is_project_owned(rel_posix):
                continue
            yield relative, path


def materialize_cursor_dir(source_root: Path, target: Path, project_id: str | None = None) -> None:
    bootstrap_adapter_imports(source_root)
    from adapters.cursor.compiler.install_support import compile_cursor_tree

    profile = compile_profile_for_target(source_root, target, project_id=project_id)
    compile_cursor_tree(source_root, target / ".cursor", profile)


@dataclass(frozen=True)
class CopyPlanEntry:
    action: str
    relative: Path
    source: Path
    destination: Path


def build_copy_plan(
    source_root: Path,
    target: Path,
    *,
    compile_cursor: bool = True,
) -> tuple[list[CopyPlanEntry], list[str]]:
    entries: list[CopyPlanEntry] = []
    managed: list[str] = []
    for relative, source in iter_managed_source_files(
        source_root, target, compile_cursor=compile_cursor
    ):
        rel_posix = relative.as_posix()
        managed.append(rel_posix)
        destination = target / relative
        if not destination.exists():
            action = "add"
        elif destination.read_bytes() != source.read_bytes():
            action = "update"
        else:
            action = "unchanged"
        entries.append(CopyPlanEntry(action, relative, source, destination))
    managed.append(LEGACY_VERSION_REL.as_posix())
    managed.append(INSTALLATION_RECORD_FILE.as_posix())
    return entries, sorted(set(managed))


def detect_obsolete_managed(old_managed: set[str], new_managed: set[str]) -> list[str]:
    return sorted(path for path in old_managed - new_managed)
