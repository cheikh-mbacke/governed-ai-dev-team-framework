"""Safe project-relative path resolution (Document 11 §8)."""

from __future__ import annotations

from pathlib import Path

from governed_ai.core.commands.errors import ErrorCode, GatewayError


def resolve_under_root(
    root: Path,
    relative: str | Path,
    *,
    forbidden_roots: list[Path] | tuple[Path, ...] | None = None,
) -> Path:
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
    for forbidden in forbidden_roots or ():
        forbidden_resolved = Path(forbidden).resolve()
        if forbidden_resolved == root_resolved:
            continue
        try:
            candidate.relative_to(forbidden_resolved)
        except ValueError:
            continue
        raise GatewayError(
            ErrorCode.INVALID_SCHEMA,
            "path resolves outside member root into another tree",
            "/target",
        )
    return candidate


def resolve_under_member(
    member_root: Path,
    relative: str | Path,
    *,
    instance_root: Path | None = None,
    other_member_roots: list[Path] | tuple[Path, ...] | None = None,
) -> Path:
    """Resolve a product path inside one member; never into the instance or siblings."""
    forbidden: list[Path] = list(other_member_roots or [])
    if instance_root is not None:
        instance = Path(instance_root).resolve()
        member = Path(member_root).resolve()
        if instance != member:
            try:
                member.relative_to(instance)
            except ValueError:
                forbidden.append(instance)
    return resolve_under_root(member_root, relative, forbidden_roots=forbidden)
