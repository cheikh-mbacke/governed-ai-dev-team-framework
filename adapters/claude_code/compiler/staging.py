"""Staging helpers and pre-install validation for the Claude Code Adaptateur (AD-002, AD-012).

``sha256_bytes``/``resolve_under_staging`` come from the shared, tool-agnostic
``governed_ai.adapters.common.staging`` module (Document 11 §5 rule 3).
``artifact_kind``/``REQUIRED_TOP_LEVEL``/``validate_pre_install`` stay local:
they encode the ``.claude/`` tree shape, which is specific to this Adaptateur.

Scope note: agent frontmatter, skills, hooks and ``settings.json`` are
compiled. Cursor's ``.mdc`` rules (all ``alwaysApply: true``) have no
direct Claude Code file-per-rule equivalent verified here, so their content
is merged into ``CLAUDE.md`` instead — the one context-injection mechanism
that is verified to load at every session start — rather than guessing at
an unverified ``.claude/rules/*.md`` path-scoping mechanism.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governed_ai.adapters.common.staging import resolve_under_staging, sha256_bytes

REQUIRED_TOP_LEVEL = (".claude/settings.json",)


def artifact_kind(rel_posix: str) -> str:
    if rel_posix.startswith(".claude/agents/") and rel_posix.endswith(".md"):
        return "agent"
    if "/skills/" in rel_posix and rel_posix.endswith("SKILL.md"):
        return "skill"
    if rel_posix.startswith(".claude/hooks/"):
        return "hook"
    if rel_posix == ".claude/settings.json":
        return "settings"
    if rel_posix == ".claude/CLAUDE.md":
        return "claude_md"
    return "adapter_file"


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

    for required_kind in ("agent", "skill", "hook"):
        if required_kind not in kinds:
            raise ValueError(f"required artifact kind missing from manifest: {required_kind}")
