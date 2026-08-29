"""Render Cursor agent frontmatter from bundle RoleDefinitionRevision."""

from __future__ import annotations

import re
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def parse_frontmatter(raw: str) -> tuple[list[tuple[str, str]], str]:
    """Return ordered frontmatter pairs and body text."""
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return [], raw
    block = match.group(1)
    body = match.group(2)
    pairs: list[tuple[str, str]] = []
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        pairs.append((key.strip(), value.strip()))
    return pairs, body


def _expected_readonly(product_level: str) -> bool:
    return product_level == "none"


def render_agent_from_role(template_text: str, role: dict[str, Any]) -> str:
    """Apply bundle-derived frontmatter fields; preserve template key order and body."""
    pairs, body = parse_frontmatter(template_text)
    if not pairs:
        return template_text

    readonly = "true" if _expected_readonly(role["writes"]["product"]["level"]) else "false"
    model = str(role.get("model_preference", "inherit"))
    name = str(role["role_id"])

    updates = {
        "name": name,
        "model": model,
        "readonly": readonly,
    }

    rendered_pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in pairs:
        if key in updates:
            rendered_pairs.append((key, updates[key]))
            seen.add(key)
        else:
            rendered_pairs.append((key, value))
            seen.add(key)

    for key, value in updates.items():
        if key not in seen:
            rendered_pairs.append((key, value))

    lines = ["---"]
    for key, value in rendered_pairs:
        lines.append(f"{key}: {value}")
    lines.append("---")
    if body.startswith("\n"):
        return "\n".join(lines) + body
    return "\n".join(lines) + "\n" + body
