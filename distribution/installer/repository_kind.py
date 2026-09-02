"""Detect repository_kind and guard install/update targets."""

from __future__ import annotations

from pathlib import Path

from distribution.installer.fabrication_layout import (
    FRAMEWORK_SOURCE_KIND,
    read_repository_kind,
)


def framework_source_install_error(source_root: Path, target: Path) -> str | None:
    """Return an error message when install/update must not run on this target."""
    source_root = source_root.resolve()
    target = target.resolve()
    if target == source_root:
        return (
            "Install aborted: target is the framework source repository root. "
            "Use a separate directory or another repository as the install target."
        )
    kind = read_repository_kind(target)
    if kind == FRAMEWORK_SOURCE_KIND:
        return (
            "Install aborted: target declares repository_kind framework_source. "
            "The framework source repository is not an install target."
        )
    return None


__all__ = ["FRAMEWORK_SOURCE_KIND", "framework_source_install_error", "read_repository_kind"]
