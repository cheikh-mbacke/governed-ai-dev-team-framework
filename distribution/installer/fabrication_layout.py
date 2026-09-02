"""Framework-source repository layout (fabrication anchor + installable payload)."""

from __future__ import annotations

from pathlib import Path

FABRIC_DIR_NAME = ".fabric"
FABRIC_PROFILE_REL = ".fabric/project-profile.yaml"
FABRIC_VERSION_REL = ".fabric/framework-version.json"
PAYLOAD_ROOT_REL = "distribution/payload"
PAYLOAD_AI_TEAM_REL = "distribution/payload/.ai-team"
PAYLOAD_SEEDS_REL = "distribution/payload/seeds"

FRESH_PROJECT_SEED_SOURCES: tuple[tuple[str, str], ...] = (
    ("distribution/payload/seeds/project-profile.yaml", ".ai-team/project-profile.yaml"),
    ("distribution/payload/seeds/project-state.yaml", ".ai-team/state/project-state.yaml"),
    (
        "distribution/payload/seeds/source-registry.yaml",
        ".ai-team/sources/source-registry.yaml",
    ),
)

FRAMEWORK_SOURCE_KIND = "framework_source"


def fabric_dir(root: Path) -> Path:
    return root / FABRIC_DIR_NAME


def payload_ai_team_dir(root: Path) -> Path:
    return root / "distribution" / "payload" / ".ai-team"


def payload_seeds_dir(root: Path) -> Path:
    return root / "distribution" / "payload" / "seeds"


def profile_path(root: Path) -> Path | None:
    fabric_profile = root / ".fabric" / "project-profile.yaml"
    if fabric_profile.is_file():
        return fabric_profile
    client_profile = root / ".ai-team" / "project-profile.yaml"
    if client_profile.is_file():
        return client_profile
    return None


def read_repository_kind(root: Path) -> str | None:
    profile = profile_path(root)
    if profile is None:
        return None
    for line in profile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


def is_framework_source_repo(root: Path) -> bool:
    return read_repository_kind(root) == FRAMEWORK_SOURCE_KIND


def source_version_file(root: Path) -> Path:
    if is_framework_source_repo(root):
        return root / ".fabric" / "framework-version.json"
    return root / ".ai-team" / "framework-version.json"


def source_ai_team_dir(root: Path) -> Path:
    """Editable .ai-team payload tree on framework source; client path otherwise."""
    payload = payload_ai_team_dir(root)
    if is_framework_source_repo(root) and payload.is_dir():
        return payload
    return root / ".ai-team"


def source_constitution_path(root: Path) -> Path:
    return source_ai_team_dir(root) / "constitution" / "constitution.yaml"


def reject_root_ai_team_on_framework_source(root: Path) -> str | None:
    if not is_framework_source_repo(root):
        return None
    legacy = root / ".ai-team"
    if legacy.exists():
        return (
            "framework_source repository must not contain a root .ai-team/ directory; "
            "use .fabric/ for fabrication metadata and distribution/payload/.ai-team/ "
            "for the installable payload."
        )
    return None


__all__ = [
    "FABRIC_DIR_NAME",
    "FABRIC_PROFILE_REL",
    "FABRIC_VERSION_REL",
    "FRESH_PROJECT_SEED_SOURCES",
    "FRAMEWORK_SOURCE_KIND",
    "PAYLOAD_AI_TEAM_REL",
    "PAYLOAD_ROOT_REL",
    "PAYLOAD_SEEDS_REL",
    "fabric_dir",
    "is_framework_source_repo",
    "payload_ai_team_dir",
    "payload_seeds_dir",
    "profile_path",
    "read_repository_kind",
    "reject_root_ai_team_on_framework_source",
    "source_ai_team_dir",
    "source_constitution_path",
    "source_version_file",
]
