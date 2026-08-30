"""Safe project-relative path resolution (Document 11 §8)."""

from __future__ import annotations

from pathlib import Path

from governed_ai.core.commands.errors import ErrorCode, GatewayError


def resolve_under_root(root: Path, relative: str | Path) -> Path:
    rel = Path(relative)
    if rel.is_absolute():
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "absolute paths are not allowed", "/target")
    if ".." in rel.parts:
        raise GatewayError(ErrorCode.INVALID_SCHEMA, "path traversal is not allowed", "/target")
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "path resolves outside project root",
            "/target",
        ) from exc
    if candidate.is_symlink():
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "symlink targets are not allowed",
            "/target",
        )
    return candidate
