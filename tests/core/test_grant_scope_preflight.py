"""Grant and Work Unit scope must meet before an unattended run starts."""

from __future__ import annotations

from pathlib import Path

from governed_ai.core.execution_gateway.scope import conflicting_grant_scopes
from governed_ai.core.execution_gateway.verification import (
    verification_failure_outside_workspace,
)


def test_grant_that_misses_every_work_unit_is_reported() -> None:
    units = [
        {"id": "WU-A", "scope": {"include": ["services/api/**"], "exclude": []}},
        {"id": "WU-B", "scope": {"include": ["apps/web/**"], "exclude": []}},
    ]
    conflicts = conflicting_grant_scopes(
        units,
        grant_allowed_paths=["docs/**"],
        grant_axis_present=True,
    )
    assert len(conflicts) == 2
    assert conflicts[0].startswith("WU-A:")
    assert "do not intersect" in conflicts[0]


def test_absent_grant_axis_does_not_block() -> None:
    units = [{"id": "WU-A", "scope": {"include": ["src/**"], "exclude": []}}]
    assert (
        conflicting_grant_scopes(
            units,
            grant_allowed_paths=None,
            grant_axis_present=False,
        )
        == []
    )


def test_overlapping_grant_is_not_a_conflict() -> None:
    units = [{"id": "WU-A", "scope": {"include": ["src/**"], "exclude": []}}]
    assert (
        conflicting_grant_scopes(
            units,
            grant_allowed_paths=["src/api/**", "docs/**"],
            grant_axis_present=True,
        )
        == []
    )


def test_unwritable_user_profile_cache_is_outside_the_workspace(tmp_path: Path) -> None:
    transcript = "EACCES: permission denied, mkdir '/home/dev/.cache/tool/index'"
    assert verification_failure_outside_workspace(transcript, tmp_path)


def test_permission_error_inside_the_workspace_stays_a_product_failure(tmp_path: Path) -> None:
    target = tmp_path / "src" / "app.txt"
    transcript = f"Permission denied: {target}"
    assert not verification_failure_outside_workspace(transcript, tmp_path)


def test_tool_binary_permission_is_not_a_user_profile_cache(tmp_path: Path) -> None:
    transcript = "permission denied: /usr/bin/node"
    assert not verification_failure_outside_workspace(transcript, tmp_path)
