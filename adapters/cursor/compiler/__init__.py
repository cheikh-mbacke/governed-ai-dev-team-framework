"""Cursor bundle → staged .cursor/ compiler (Document 13 Phase 4 §4.1)."""

from adapters.cursor.compiler.compile import compile_manifest
from adapters.cursor.compiler.parity import (
    GoldenManifest,
    ShadowReport,
    build_golden_manifest,
    shadow_compare,
    verify_golden_compile,
)

__all__ = [
    "GoldenManifest",
    "ShadowReport",
    "build_golden_manifest",
    "compile_manifest",
    "shadow_compare",
    "verify_golden_compile",
]
