"""WU-P4-CONFORMANCE — Cursor adapter universal conformance harness tests."""

from __future__ import annotations

from pathlib import Path

from governed_ai.adapters.cursor import CursorAdapter
from tests.adapters import conformance_suite as suite


def _cursor_factory(
    project_root: Path,
    *,
    bundle_dir: Path | None = None,
    staging_dir: Path | None = None,
) -> CursorAdapter:
    return CursorAdapter(
        project_root=project_root,
        bundle_dir=bundle_dir,
        staging_dir=staging_dir,
        templates_root=suite.TEMPLATES_ROOT,
    )


def test_ad001_descriptor() -> None:
    suite.run_ad001_descriptor(_cursor_factory(suite.REPO_ROOT))


def test_ad002_compile(tmp_path: Path) -> None:
    suite.run_ad002_compile(_cursor_factory, tmp_path)


def test_ad003_deterministic_compile(tmp_path: Path) -> None:
    suite.run_ad003_deterministic_compile(_cursor_factory, tmp_path)


def test_ad004_restrictive_capability_available() -> None:
    suite.run_ad004_restrictive_capability_available(
        _cursor_factory(suite.REPO_ROOT, bundle_dir=suite.BUNDLE_V1)
    )


def test_ad005_impossible_capability_blocks(tmp_path: Path) -> None:
    suite.run_ad005_impossible_capability_blocks(
        _cursor_factory(suite.REPO_ROOT, bundle_dir=suite.BUNDLE_V1),
        tmp_path,
        _cursor_factory,
    )


def test_ad006_readonly_blocks_product_writes(tmp_path: Path) -> None:
    suite.run_ad006_readonly_blocks_product_writes(_cursor_factory, tmp_path)


def test_ad007_mediated_record_observation(tmp_path: Path) -> None:
    suite.run_ad007_mediated_record_observation(_cursor_factory, tmp_path)


def test_ad008_human_auth_required(tmp_path: Path) -> None:
    suite.run_ad008_human_auth_required(_cursor_factory, tmp_path)


def test_ad009_runtime_result_complete(tmp_path: Path) -> None:
    suite.run_ad009_runtime_result_complete(_cursor_factory, tmp_path)


def test_ad010_agent_done_claim_leaves_core_unchanged(tmp_path: Path) -> None:
    suite.run_ad010_agent_done_claim_leaves_core_unchanged(_cursor_factory, tmp_path)


def test_ct008_unsupported_protocol_blocks_execution(tmp_path: Path) -> None:
    suite.run_ct008_unsupported_protocol_blocks_execution(_cursor_factory, tmp_path)


def test_ct009_capability_not_enforceable_reported() -> None:
    suite.run_ct009_capability_not_enforceable_reported(
        _cursor_factory(suite.REPO_ROOT, bundle_dir=suite.BUNDLE_V1)
    )


def test_auth_smoke_adapter_only(tmp_path: Path) -> None:
    suite.run_auth_smoke_adapter_only(_cursor_factory, tmp_path)


def test_full_conformance_suite(tmp_path: Path) -> None:
    suite.run_full_conformance(_cursor_factory, tmp_path)
