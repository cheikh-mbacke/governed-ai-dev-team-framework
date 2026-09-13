"""Pure path policy shared by authorization and execution boundaries."""

from __future__ import annotations

import fnmatch

PROTECTED_PATH_PREFIXES = (
    ".ai-team/constitution/",
    ".ai-team/schemas/",
    ".ai-team/contracts/",
    ".ai-team/run-authorization-grants/",
    ".ai-team/runs/",
    ".ai-team/state/",
)

CONTROL_PLANE_ONLY_PATH_PREFIXES = (
    *PROTECTED_PATH_PREFIXES,
    ".ai-team/work-units/",
)


def normalize_repo_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def sanitize_allowed_paths(patterns: list[str] | tuple[str, ...] | None) -> list[str]:
    """Remove grants rooted in Control-Plane-only governance paths."""
    sanitized: list[str] = []
    for raw_pattern in patterns or []:
        pattern = normalize_repo_path(str(raw_pattern)).strip()
        if not pattern:
            continue
        positions = [position for char in "*?[" if (position := pattern.find(char)) >= 0]
        static_prefix = pattern[: min(positions)] if positions else pattern
        overlaps_control_plane = any(
            static_prefix.startswith(prefix)
            or fnmatch.fnmatchcase(f"{prefix}__boundary_probe__", pattern)
            for prefix in CONTROL_PLANE_ONLY_PATH_PREFIXES
        )
        if overlaps_control_plane:
            continue
        if pattern not in sanitized:
            sanitized.append(pattern)
    return sanitized
