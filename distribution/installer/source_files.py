"""Managed source file enumeration and copy planning."""

from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path

from distribution.installer.constants import COPY_ITEMS, LEGACY_VERSION_REL, PROJECT_OWNED_PATTERNS
from distribution.installer.paths import (
    DIRECT_COPY_ITEMS,
    RELOCATED_COPY_FILES,
    RELOCATED_COPY_PREFIXES,
    adapter_compiler_import_root,
    compile_source_root,
    map_source_relative_to_target,
)
from distribution.installer.record import INSTALLATION_RECORD_FILE, LEGACY_VERSION_FILE


def _read_repository_kind(source_root: Path) -> str | None:
    profile = source_root / ".ai-team" / "project-profile.yaml"
    if not profile.is_file():
        return None
    for line in profile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _resolve_agents_md_source(source_root: Path) -> Path:
    template = source_root / "adapters" / "cursor" / "templates" / "AGENTS.md"
    if _read_repository_kind(source_root) == "framework_source" and template.is_file():
        return template
    return source_root / "AGENTS.md"


def bootstrap_adapter_imports(source_root: Path, target: Path | None = None) -> None:
    from distribution.installer.paths import is_installed_runtime_layout

    root = compile_source_root(source_root, target)
    import_root = adapter_compiler_import_root(source_root, target)
    entries = [str(root), str(import_root)]
    if not is_installed_runtime_layout(root):
        entries.append(str(root / "src"))
    for entry in entries:
        if entry not in sys.path:
            sys.path.insert(0, entry)


def is_project_owned(rel_posix: str) -> bool:
    if rel_posix == ".ai-team/migration-backups/.gitignore":
        return False
    if rel_posix.startswith(".ai-team/runtime/"):
        return False
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in PROJECT_OWNED_PATTERNS)


def _should_skip_source_file(relative: Path, *, skip_install_record: bool = True) -> bool:
    rel_posix = relative.as_posix()
    if "__pycache__" in relative.parts or relative.suffix == ".pyc":
        return True
    if ".transactions" in relative.parts:
        return True
    if relative == LEGACY_VERSION_FILE:
        return True
    if skip_install_record and rel_posix == INSTALLATION_RECORD_FILE.as_posix():
        return True
    if is_project_owned(rel_posix):
        return True
    return False


def _iter_direct_copy_files(source_root: Path, item: str):
    src = source_root / item
    if not src.exists():
        return
    if item == ".ai-team":
        paths = src.rglob("*")
    elif item == "scripts":
        ai_team = src / "ai-team"
        if not ai_team.is_dir():
            return
        paths = ai_team.rglob("*")
    elif item == "AGENTS.md":
        agents_src = _resolve_agents_md_source(source_root)
        if agents_src.is_file():
            yield Path("AGENTS.md"), agents_src
        return
    else:
        paths = src.rglob("*") if src.is_dir() else [src]

    for path in paths:
        if path.is_dir():
            continue
        relative = path.relative_to(source_root)
        if _should_skip_source_file(relative):
            continue
        dest_rel = map_source_relative_to_target(relative.as_posix())
        yield Path(dest_rel), path


def _iter_relocated_prefix_files(source_root: Path, src_prefix: str):
    src = source_root / src_prefix
    if not src.exists():
        return
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source_root)
        if _should_skip_source_file(relative):
            continue
        dest_rel = map_source_relative_to_target(relative.as_posix())
        yield Path(dest_rel), path


def _iter_relocated_file_items(source_root: Path):
    for src_file, _dest in RELOCATED_COPY_FILES:
        src = source_root / src_file
        if src.is_file():
            dest_rel = map_source_relative_to_target(src_file)
            yield Path(dest_rel), src


def compile_profile_for_target(source_root: Path, target: Path, project_id: str | None = None) -> dict:
    bootstrap_adapter_imports(source_root, target)
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

    handled_prefixes = {prefix for prefix, _ in RELOCATED_COPY_PREFIXES}
    handled_files = {src for src, _ in RELOCATED_COPY_FILES}

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
            bootstrap_adapter_imports(source_root, target)
            from adapters.cursor.compiler.install_support import iter_compiled_cursor_files

            compile_root = compile_source_root(source_root, target)
            for relative, path in iter_compiled_cursor_files(compile_root, profile, target=target):
                rel_posix = relative.as_posix()
                if is_project_owned(rel_posix):
                    continue
                yield relative, path
            continue

        if item in handled_prefixes:
            for relative, path in _iter_relocated_prefix_files(source_root, item):
                yield relative, path
            continue

        if item in handled_files:
            continue

        if item in DIRECT_COPY_ITEMS or item == "scripts":
            yield from _iter_direct_copy_files(source_root, item)

    yield from _iter_relocated_file_items(source_root)


def materialize_cursor_dir(source_root: Path, target: Path, project_id: str | None = None) -> None:
    bootstrap_adapter_imports(source_root, target)
    from adapters.cursor.compiler.install_support import compile_cursor_tree

    profile = compile_profile_for_target(source_root, target, project_id=project_id)
    compile_root = compile_source_root(source_root, target)
    compile_cursor_tree(compile_root, target / ".cursor", profile, target=target)


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
    project_id: str | None = None,
) -> tuple[list[CopyPlanEntry], list[str]]:
    entries: list[CopyPlanEntry] = []
    managed: list[str] = []
    for relative, source in iter_managed_source_files(
        source_root, target, project_id=project_id, compile_cursor=compile_cursor
    ):
        rel_posix = relative.as_posix()
        if rel_posix == "AGENTS.md":
            managed.append(rel_posix)
            destination = target / relative
            action = "merge" if destination.exists() else "add"
            entries.append(CopyPlanEntry(action, relative, source, destination))
            continue
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
