"""Detect repository_kind and guard install/update targets."""

from __future__ import annotations

from pathlib import Path

FRAMEWORK_SOURCE_KIND = "framework_source"


def read_repository_kind(root: Path) -> str | None:
    profile = root / ".ai-team" / "project-profile.yaml"
    if not profile.is_file():
        return None
    for line in profile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


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
