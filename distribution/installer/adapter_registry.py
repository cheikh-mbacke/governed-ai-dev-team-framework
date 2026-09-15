"""Per-Adaptateur registration for the installer (Document 11 §4).

Centralizes what used to be Cursor literals scattered across
``source_files.py``/``apply.py`` so a second Adaptateur is a registry entry,
not a parallel set of hardcoded branches. Compile functions are resolved via
lazy imports (mirroring the existing ``bootstrap_adapter_imports`` pattern)
to avoid importing an Adaptateur's compiler before ``sys.path`` is ready.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class _CompileTreeFn(Protocol):
    def __call__(
        self,
        source_root: Path,
        destination: Path,
        project_profile: dict[str, Any] | None = None,
        *,
        target: Path | None = None,
    ) -> dict[str, Any]: ...


class _IterFilesFn(Protocol):
    def __call__(
        self,
        source_root: Path,
        project_profile: dict[str, Any] | None = None,
        *,
        target: Path | None = None,
    ) -> Iterator[tuple[Path, Path]]: ...


@dataclass(frozen=True)
class AdapterRegistration:
    id: str
    compiled_dir_item: str  # e.g. ".cursor" — top-level compiled output dir
    source_item: str  # e.g. "adapters/cursor" — relocated runtime source
    compile_tree: _CompileTreeFn
    iter_files: _IterFilesFn


def _cursor_compile_tree(
    source_root: Path,
    destination: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    target: Path | None = None,
) -> dict[str, Any]:
    from adapters.cursor.compiler.install_support import compile_cursor_tree

    return compile_cursor_tree(source_root, destination, project_profile, target=target)


def _cursor_iter_files(
    source_root: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    target: Path | None = None,
) -> Iterator[tuple[Path, Path]]:
    from adapters.cursor.compiler.install_support import iter_compiled_cursor_files

    yield from iter_compiled_cursor_files(source_root, project_profile, target=target)


def _claude_code_compile_tree(
    source_root: Path,
    destination: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    target: Path | None = None,
) -> dict[str, Any]:
    from adapters.claude_code.compiler.install_support import compile_claude_code_tree

    return compile_claude_code_tree(source_root, destination, project_profile, target=target)


def _claude_code_iter_files(
    source_root: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    target: Path | None = None,
) -> Iterator[tuple[Path, Path]]:
    from adapters.claude_code.compiler.install_support import iter_compiled_claude_code_files

    yield from iter_compiled_claude_code_files(source_root, project_profile, target=target)


ADAPTERS: dict[str, AdapterRegistration] = {
    "cursor": AdapterRegistration(
        id="cursor",
        compiled_dir_item=".cursor",
        source_item="adapters/cursor",
        compile_tree=_cursor_compile_tree,
        iter_files=_cursor_iter_files,
    ),
    "claude-code": AdapterRegistration(
        id="claude-code",
        compiled_dir_item=".claude",
        source_item="adapters/claude_code",
        compile_tree=_claude_code_compile_tree,
        iter_files=_claude_code_iter_files,
    ),
}


def adapter_registration(adapter_id: str) -> AdapterRegistration:
    try:
        return ADAPTERS[adapter_id]
    except KeyError:
        raise ValueError(f"unknown active_adapter_id: {adapter_id!r}") from None


__all__ = ["ADAPTERS", "AdapterRegistration", "adapter_registration"]
