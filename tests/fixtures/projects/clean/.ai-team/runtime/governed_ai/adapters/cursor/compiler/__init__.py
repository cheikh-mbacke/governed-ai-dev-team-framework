"""Cursor bundle → staged .cursor/ compiler (Document 13 Phase 4 §4.1)."""

from .compile import compile_manifest
from .ensemble_workspace import render_code_workspace, write_active_ensemble_workspace
from .parity import (
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
    "render_code_workspace",
    "shadow_compare",
    "verify_golden_compile",
    "write_active_ensemble_workspace",
]
