"""Render Claude Code subagent frontmatter from bundle RoleDefinitionRevision.

Frontmatter mapping (Document 3 §3, revalidated 2026-09-15):

======================  ====================  ===============================
Role field              Cursor frontmatter     Claude Code frontmatter
======================  ====================  ===============================
``role_id``             ``name``               ``name``
(preserved from template) ``description``      ``description``
``model_preference``    ``model``              ``model``
``writes.product.level````readonly: true/false``  ``tools:`` — ``Read, Grep,
                                                    Glob`` when ``level ==
                                                    "none"``; omitted (full
                                                    inheritance) otherwise.
======================  ====================  ===============================

Path-level scoping (``writes.product.paths``) is not translated here — see
Document 3 §"Grain Claude Code résolu partiellement": it needs composing with
``settings.json`` ``permissions.deny`` rules, planned as a follow-up
increment, not the per-subagent ``tools`` list alone.
"""

from __future__ import annotations

import re
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)

# Source templates are copied from adapters/cursor/templates/.cursor/agents/ as a
# starting point and still carry Cursor-only frontmatter keys (e.g. `readonly`,
# meaningless — and misleading — in a Claude Code subagent). Drop them on render
# rather than passing them through.
_DROP_KEYS = frozenset({"readonly"})


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


def _tools_for_role(product_level: str) -> str | None:
    """Hard boundary for what the subagent cannot do (verified: a tool absent
    from this list is not callable, not merely advisory). Path-level scoping
    is a separate, unaddressed gap — see module docstring."""
    if product_level == "none":
        return "Read, Grep, Glob"
    return None


def render_agent_from_role(template_text: str, role: dict[str, Any]) -> str:
    """Apply bundle-derived frontmatter fields; preserve template key order and body."""
    pairs, body = parse_frontmatter(template_text)
    if not pairs:
        return template_text

    product_level = str(role["writes"]["product"]["level"])
    model = str(role.get("model_preference", "inherit"))
    name = str(role["role_id"])

    updates: dict[str, str] = {"name": name, "model": model}
    tools = _tools_for_role(product_level)
    if tools is not None:
        updates["tools"] = tools

    rendered_pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in pairs:
        if key in _DROP_KEYS:
            continue
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
