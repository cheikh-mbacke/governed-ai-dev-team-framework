"""Utilities shared by every Adaptateur (Document 11 §5 rule 3).

Nothing under this package may reference a specific tool (Cursor, Claude Code,
Codex). It exists so `adapters.cursor` and `adapters.claude_code` do not need
to depend on each other for logic that is genuinely tool-agnostic.
"""

from __future__ import annotations
