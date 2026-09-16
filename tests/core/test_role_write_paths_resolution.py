"""resolve_role_write_paths — Document 12 §2.2 symbolic path resolution.

Role bundles declare ``writes.product.paths`` symbolically (e.g.
``["<work-unit-scope>"]``) because the concrete paths only exist once a Work
Unit does. These tests cover the resolver directly; see
test_execution_gateway.py for its effect on ``compile_request``'s
``contract.effective_scope``, and test_boundary.py for the (currently
compile-time-only — see execution_bridge.py's comment above
``gateway.execute()``) enforcement classification it feeds.
"""

from __future__ import annotations

from governed_ai.core.execution_gateway.scope import resolve_role_write_paths


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
