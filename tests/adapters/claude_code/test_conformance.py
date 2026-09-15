"""Claude Code adapter — universal conformance harness (Document 14 §9 AD-001..010, CT-008/009).

v1 (pilot) scope: mirrors ``tests/adapters/cursor/test_conformance.py`` but
calls the individual ``run_adXXX``/``run_ctXXX`` functions rather than
``run_full_conformance`` — this pilot ships no ``auth-smoke``-equivalent
artefact, so ``run_auth_smoke_adapter_only`` (Cursor-specific artefact path)
does not apply. See plan snug-knitting-catmull.
"""

from __future__ import annotations

from pathlib import Path

from adapters.claude_code.compiler.staging import (
    validate_pre_install as claude_code_validate_pre_install,
)
from tests.adapters import conformance_suite as suite

from governed_ai.adapters.claude_code import ClaudeCodeAdapter

REPO_ROOT = suite.REPO_ROOT
ADAPTER_MANIFEST = REPO_ROOT / "adapters" / "claude_code" / "manifest.json"
TEMPLATES_ROOT = REPO_ROOT / "adapters" / "claude_code" / "templates"
ADAPTER_ID = "claude-code"
ADAPTER_VERSION = "0.1.0"


def _claude_code_factory(
    project_root: Path,
    *,
    bundle_dir: Path | None = None,
    staging_dir: Path | None = None,
) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(
        project_root=project_root,
        bundle_dir=bundle_dir,
        staging_dir=staging_dir,
        templates_root=TEMPLATES_ROOT,
    )


def test_ad001_descriptor() -> None:
    suite.run_ad001_descriptor(
        _claude_code_factory(REPO_ROOT), manifest_path=ADAPTER_MANIFEST
    )


def test_ad002_compile(tmp_path: Path) -> None:
    suite.run_ad002_compile(
        _claude_code_factory,
        tmp_path,
        expected_adapter_id=ADAPTER_ID,
        validate_pre_install_fn=claude_code_validate_pre_install,
    )


def test_ad003_deterministic_compile(tmp_path: Path) -> None:
    suite.run_ad003_deterministic_compile(_claude_code_factory, tmp_path)


def test_ad004_restrictive_capability_available() -> None:
    suite.run_ad004_restrictive_capability_available(
        _claude_code_factory(suite.REPO_ROOT, bundle_dir=suite.BUNDLE_V1)
    )


def test_ad005_impossible_capability_blocks(tmp_path: Path) -> None:
    suite.run_ad005_impossible_capability_blocks(
        _claude_code_factory(suite.REPO_ROOT, bundle_dir=suite.BUNDLE_V1),
        tmp_path,
        _claude_code_factory,
    )


def test_ad006_readonly_blocks_product_writes(tmp_path: Path) -> None:
    suite.run_ad006_readonly_blocks_product_writes(_claude_code_factory, tmp_path)


def test_ad007_mediated_record_observation(tmp_path: Path) -> None:
    suite.run_ad007_mediated_record_observation(_claude_code_factory, tmp_path)


def test_ad008_human_auth_required(tmp_path: Path) -> None:
    suite.run_ad008_human_auth_required(_claude_code_factory, tmp_path)


def test_ad009_runtime_result_complete(tmp_path: Path) -> None:
    suite.run_ad009_runtime_result_complete(
        _claude_code_factory, tmp_path, expected_adapter_id=ADAPTER_ID
    )


def test_ad010_agent_done_claim_leaves_core_unchanged(tmp_path: Path) -> None:
    suite.run_ad010_agent_done_claim_leaves_core_unchanged(_claude_code_factory, tmp_path)


def test_ct008_unsupported_protocol_blocks_execution(tmp_path: Path) -> None:
    suite.run_ct008_unsupported_protocol_blocks_execution(_claude_code_factory, tmp_path)


def test_ct009_capability_not_enforceable_reported() -> None:
    suite.run_ct009_capability_not_enforceable_reported(
        _claude_code_factory(suite.REPO_ROOT, bundle_dir=suite.BUNDLE_V1)
    )
