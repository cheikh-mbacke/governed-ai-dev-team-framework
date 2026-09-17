"""resolve_role_write_paths — Document 12 §2.2 symbolic path resolution.

Role bundles declare ``writes.product.paths`` symbolically (e.g.
``["<work-unit-scope>"]``) because the concrete paths only exist once a Work
Unit does. These tests cover the resolver directly; see
test_execution_gateway.py for its effect on ``compile_request``'s
``contract.effective_scope``, and test_boundary.py for the (currently
compile-time-only — see execution_bridge.py's comment above
``gateway.execute()``) enforcement classification it feeds.

SPI ``resolved_scope`` must equal that compiled ``effective_scope`` at
transmission (``align_spi_resolved_scope`` / ``SpiCompatibleAdapter``).
"""

from __future__ import annotations

from typing import Any

from governed_ai.core.execution_gateway.scope import resolve_role_write_paths
from governed_ai.core.supervisor.execution_bridge import (
    SpiCompatibleAdapter,
    align_spi_resolved_scope,
)


def test_no_declared_paths_is_not_applicable() -> None:
    """writes.product.level == "none" roles declare paths=[] — that must mean
    "axis not applicable" (None), not "axis present but empty" ([]), or every
    readonly role's compile_request would hard-fail before running."""
    assert resolve_role_write_paths([], work_unit={"scope": {"include": []}}) is None
    assert resolve_role_write_paths(None, work_unit={"scope": {"include": []}}) is None


def test_bare_placeholder_resolves_to_work_unit_scope() -> None:
    assert resolve_role_write_paths(
        ["<work-unit-scope>"],
        work_unit={"scope": {"include": ["src/api/**"]}},
    ) == ["src/api/**"]


def test_bare_placeholder_with_multiple_wu_includes_expands_each() -> None:
    assert resolve_role_write_paths(
        ["<work-unit-scope>"],
        work_unit={"scope": {"include": ["src/api/**", "src/web/**"]}},
    ) == ["src/api/**", "src/web/**"]


def test_unresolvable_placeholder_is_not_applicable_not_empty() -> None:
    """A Work Unit with no scope.include yet gives the resolver nothing to
    substitute — that must defer to other axes (None), never collapse to an
    empty, always-deny axis ([])."""
    assert resolve_role_write_paths(["<work-unit-scope>"], work_unit={}) is None
    assert (
        resolve_role_write_paths(["<work-unit-scope>"], work_unit={"scope": {"include": []}})
        is None
    )


def test_placeholder_with_suffix_substitutes_and_keeps_literal_entries() -> None:
    """qa-test/test-strategist's real template: ["<work-unit-scope>/tests", "tests/"]."""
    resolved = resolve_role_write_paths(
        ["<work-unit-scope>/tests", "tests/"],
        work_unit={"scope": {"include": ["src/api/**"]}},
    )
    assert resolved == ["src/api/**/tests", "tests/"]


def test_literal_entry_survives_even_without_a_resolvable_placeholder() -> None:
    """The tests_only template's fixed "tests/" entry is still a real,
    non-empty constraint even when the WU hasn't declared scope.include yet."""
    assert resolve_role_write_paths(
        ["<work-unit-scope>/tests", "tests/"],
        work_unit={"scope": {"include": []}},
    ) == ["tests/"]


def test_reconciliation_style_placeholder_name_is_not_special_cased() -> None:
    """Any <...> token substitutes the same way — the resolver does not
    special-case "<work-unit-scope>" as a literal string match."""
    assert resolve_role_write_paths(
        ["<approved-reconciliation-scope>"],
        work_unit={"scope": {"include": ["design/**"]}},
    ) == ["design/**"]


def test_align_spi_resolved_scope_overwrites_wu_include_placeholder() -> None:
    """Document 12 §2.2: the Adaptateur must receive the compiled scope, not
    the raw Work Unit include the orchestrator stuffed in before compile."""
    merged = align_spi_resolved_scope(
        {
            "resolved_scope": ["src/**", "tests/**"],
            "contract": {"effective_scope": ["tests/**"]},
        }
    )
    assert merged["resolved_scope"] == ["tests/**"]


def test_align_spi_resolved_scope_leaves_placeholder_when_contract_has_no_list() -> None:
    merged = align_spi_resolved_scope(
        {
            "resolved_scope": ["src/**"],
            "contract": {"bundle_version": "1.0.0"},
        }
    )
    assert merged["resolved_scope"] == ["src/**"]
    merged_missing = align_spi_resolved_scope({"resolved_scope": ["src/**"]})
    assert merged_missing["resolved_scope"] == ["src/**"]


def test_spi_adapter_transmits_effective_scope_not_wu_include() -> None:
    captured: dict[str, Any] = {}

    class _Adapter:
        def execute(self, request: dict[str, Any]) -> dict[str, Any]:
            captured.update(request)
            return {"status": "succeeded"}

    SpiCompatibleAdapter(
        _Adapter(),
        spi_request={
            "protocol_version": "1.0",
            "resolved_scope": ["src/**", "tests/**"],
            "contract": {"bundle_version": "1.0.0", "role_id": "qa-test"},
        },
    ).execute(
        {
            "execution_id": "EXE-1",
            "contract": {
                "role_id": "qa-test",
                "procedure_id": "webapp-testing",
                "effective_scope": ["tests/**"],
            },
        }
    )
    assert captured["resolved_scope"] == ["tests/**"]
    assert captured["contract"]["effective_scope"] == ["tests/**"]
    assert captured["contract"]["bundle_version"] == "1.0.0"
