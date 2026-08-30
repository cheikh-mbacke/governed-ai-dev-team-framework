"""Governed AI Cursor adapter (SPI wrapper)."""

from governed_ai.adapters.cursor.adapter import CursorAdapter
from governed_ai.adapters.cursor.compile import compile_manifest

__all__ = ["CursorAdapter", "compile_manifest"]
