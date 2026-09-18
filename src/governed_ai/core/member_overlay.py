"""Thin member overlay: member-link.json and AGENTS.md pointer (Document 25)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.atomic import atomic_write_text

MEMBER_LINK_NAME = "member-link.json"
AI_TEAM_DIR_NAME = ".ai-team"
MARKER_START = "<!-- governed-ai-member:start -->"
MARKER_END = "<!-- governed-ai-member:end -->"


def _link_path(member_root: Path) -> Path:
    return member_root / AI_TEAM_DIR_NAME / MEMBER_LINK_NAME


def _agents_body(*, ensemble_id: str, member_id: str, instance_path: Path) -> str:
    return (
        f"This repository is member `{member_id}` of ensemble `{ensemble_id}`.\n"
        "Do not run `/compile-project` or `python scripts/ai-team/gov.py` here.\n"
        "Open the instance and run the client cycle from:\n"
        f"  {instance_path}\n"
    )


def merge_member_agents_md(existing: str, body: str) -> str:
    wrapped = f"{MARKER_START}\n{body.rstrip()}\n{MARKER_END}"
    if MARKER_START in existing and MARKER_END in existing:
        start = existing.find(MARKER_START)
        end = existing.find(MARKER_END) + len(MARKER_END)
        return existing[:start] + wrapped + existing[end:].lstrip("\n")
    sep = "\n\n" if existing.endswith("\n") or not existing else "\n\n"
    return existing.rstrip() + sep + wrapped + "\n"


def load_member_link(member_root: Path) -> dict[str, Any] | None:
    path = _link_path(member_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"invalid member-link at {path}: {exc}",
            "/payload/path",
        ) from exc
    if not isinstance(payload, dict):
        raise GatewayError(
            ErrorCode.INVARIANT_VIOLATION,
            f"member-link at {path} must be an object",
            "/payload/path",
        )
    return payload


def write_member_overlay(
    member_root: Path,
    *,
    instance_id: str,
    ensemble_id: str,
    member_id: str,
    instance_path: Path,
) -> None:
    """Write the non-authoritative overlay on the member Git (not instance-journaled)."""
    instance_resolved = instance_path.resolve()
    existing = load_member_link(member_root)
    if existing is not None:
        previous = existing.get("instance_path")
        if isinstance(previous, str) and previous.strip():
            previous_path = Path(previous)
            if not previous_path.is_absolute():
                previous_path = (member_root / previous_path).resolve()
            else:
                previous_path = previous_path.resolve()
            if previous_path != instance_resolved or existing.get("member_id") != member_id:
                raise GatewayError(
                    ErrorCode.CONFLICT,
                    "member already has a member-link for a different instance or member id",
                    "/payload/path",
                )
    document = {
        "schema_version": 1,
        "instance_id": instance_id,
        "ensemble_id": ensemble_id,
        "member_id": member_id,
        "instance_path": str(instance_resolved),
    }
    link_path = _link_path(member_root)
    link_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(link_path, json.dumps(document, indent=2) + "\n")

    agents_path = member_root / "AGENTS.md"
    body = _agents_body(
        ensemble_id=ensemble_id, member_id=member_id, instance_path=instance_resolved
    )
    if agents_path.is_file():
        existing_text = agents_path.read_text(encoding="utf-8")
        atomic_write_text(agents_path, merge_member_agents_md(existing_text, body))
    else:
        atomic_write_text(agents_path, f"{MARKER_START}\n{body.rstrip()}\n{MARKER_END}\n")
