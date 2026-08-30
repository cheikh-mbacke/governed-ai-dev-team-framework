"""AGENTS.md managed-block merge for install and update."""

from __future__ import annotations

from pathlib import Path

MARKER_START = "<!-- governed-ai:start -->"
MARKER_END = "<!-- governed-ai:end -->"


def extract_managed_block(content: str) -> str | None:
    start = content.find(MARKER_START)
    end = content.find(MARKER_END)
    if start == -1 or end == -1 or end < start:
        return None
    return content[start + len(MARKER_START) : end].strip("\n")


def wrap_managed_block(body: str) -> str:
    inner = body.strip("\n")
    return f"{MARKER_START}\n{inner}\n{MARKER_END}"


def merge_agents_md(existing: str, managed_body: str) -> str:
    wrapped = wrap_managed_block(managed_body)
    if MARKER_START in existing and MARKER_END in existing:
        start = existing.find(MARKER_START)
        end = existing.find(MARKER_END) + len(MARKER_END)
        return existing[:start] + wrapped + existing[end:].lstrip("\n")
    sep = "\n\n" if existing.endswith("\n") or not existing else "\n\n"
    return existing.rstrip() + sep + wrapped + "\n"


def write_agents_md(destination: Path, source: Path) -> None:
    managed_body = source.read_text(encoding="utf-8")
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        destination.write_text(merge_agents_md(existing, managed_body), encoding="utf-8")
    else:
        # Always write with markers, even when creating fresh — otherwise the
        # next update's merge_agents_md() won't find MARKER_START/END in the
        # existing file and will append a second, duplicate managed block.
        destination.write_text(wrap_managed_block(managed_body) + "\n", encoding="utf-8")
