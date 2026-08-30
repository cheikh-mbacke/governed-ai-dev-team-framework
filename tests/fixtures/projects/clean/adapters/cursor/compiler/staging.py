"""Staging helpers and pre-install validation (AD-002, AD-012)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL = (
    ".cursor/hooks.json",
    ".cursor/permissions.json",
    ".cursor/cli.json",
)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def artifact_kind(rel_posix: str) -> str:
    if rel_posix.startswith(".cursor/agents/") and rel_posix.endswith(".md"):
        return "agent"
    if "/skills/" in rel_posix and rel_posix.endswith("SKILL.md"):
        return "skill"
    if rel_posix.startswith(".cursor/rules/") and rel_posix.endswith(".mdc"):
        return "rule"
    if rel_posix.startswith(".cursor/hooks/"):
        return "hook"
    if rel_posix == ".cursor/hooks.json":
        return "hooks_config"
    if rel_posix == ".cursor/permissions.json":
        return "permissions"
    if rel_posix == ".cursor/cli.json":
        return "cli_config"
    return "adapter_file"


def resolve_under_staging(staging_root: Path, rel_path: str) -> Path:
    """Resolve a manifest-relative path and reject escapes (AD-012)."""
    staging_resolved = staging_root.resolve()
    candidate = (staging_root / rel_path).resolve()
    if not candidate.is_relative_to(staging_resolved):
        raise ValueError(f"artifact path escapes staging: {rel_path}")
    return candidate


def validate_pre_install(staging_root: Path, manifest: dict[str, Any]) -> None:
    """Ensure manifest paths stay under staging and required artefacts exist."""
    artifacts = manifest.get("artifacts") or []
    if not artifacts:
        raise ValueError("artifact manifest is empty")

    seen_paths: set[str] = set()
    kinds: set[str] = set()
    for entry in artifacts:
        rel = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(rel, str) or not rel:
            raise ValueError("artifact entry missing path")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ValueError(f"artifact entry missing sha256: {rel}")

        target = resolve_under_staging(staging_root, rel)
        if not target.is_file():
            raise ValueError(f"staged artifact missing on disk: {rel}")

        on_disk = sha256_bytes(target.read_bytes())
        if on_disk != digest:
            raise ValueError(f"staged artifact hash mismatch: {rel}")

        seen_paths.add(rel)
        kinds.add(artifact_kind(rel))

    for required in REQUIRED_TOP_LEVEL:
        if required not in seen_paths:
            raise ValueError(f"required staged artifact missing from manifest: {required}")

    for required_kind in ("agent", "skill", "rule", "hook"):
        if required_kind not in kinds:
            raise ValueError(f"required artifact kind missing from manifest: {required_kind}")
