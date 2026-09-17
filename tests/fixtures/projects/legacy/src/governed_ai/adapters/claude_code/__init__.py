"""Governed AI Claude Code adapter (SPI wrapper) — pilot skeleton."""

from governed_ai.adapters.claude_code.adapter import ClaudeCodeAdapter
from governed_ai.adapters.claude_code.compile import compile_manifest

__all__ = ["ClaudeCodeAdapter", "compile_manifest"]
