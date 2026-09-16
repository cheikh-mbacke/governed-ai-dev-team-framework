"""Execution boundary classification — product vs governed outputs."""

from __future__ import annotations

from governed_ai.core.orchestrator.boundary import (
    boundary_error_for_changed_files,
    classify_changed_path,
    is_path_scope_pattern,
)


def test_path_scope_pattern_distinguishes_globs_from_prose() -> None:
    assert is_path_scope_pattern("src/**")
    assert is_path_scope_pattern("site-vitrine/")
    assert is_path_scope_pattern("package.json")
    assert is_path_scope_pattern("src")
    assert not is_path_scope_pattern("Invest public page")
    assert not is_path_scope_pattern("decision-menu automation")


def test_evidence_for_active_wu_is_governed_output() -> None:
    assert (
        classify_changed_path(
            ".ai-team/evidence/WU-INV-09/ac-01.md",
            work_unit_id="WU-INV-09",
            scope_include=["site-vitrine/**"],
            scope_exclude=[],
            allowed_paths=["site-vitrine/**"],
        )
        == "allowed_governed"
    )


def test_evidence_for_other_wu_is_not_governed_for_active_wu() -> None:
    assert (
        classify_changed_path(
            ".ai-team/evidence/WU-OTHER/ac-01.md",
            work_unit_id="WU-INV-09",
            scope_include=["site-vitrine/**"],
            scope_exclude=[],
            allowed_paths=["site-vitrine/**"],
        )
        == "forbidden_scope"
    )


def test_work_unit_yaml_mutation_is_forbidden() -> None:
    assert (
        classify_changed_path(
            ".ai-team/work-units/WU-INV-09.yaml",
            work_unit_id="WU-INV-09",
            scope_include=[".ai-team/**"],
            scope_exclude=[],
            allowed_paths=[".ai-team/**"],
        )
        == "forbidden_governance"
    )


def test_product_write_requires_include_and_envelope_when_both_set() -> None:
    assert (
        classify_changed_path(
            "site-vitrine/app/page.tsx",
            work_unit_id="WU-INV-09",
            scope_include=["site-vitrine/**"],
            scope_exclude=[],
            allowed_paths=["site-vitrine/**"],
        )
        == "allowed_product"
    )
    assert (
        classify_changed_path(
            "backend/pom.xml",
            work_unit_id="WU-INV-09",
            scope_include=["site-vitrine/**"],
            scope_exclude=[],
            allowed_paths=["site-vitrine/**", "backend/**"],
        )
        == "forbidden_scope"
    )
    assert (
        classify_changed_path(
            "site-vitrine/app/page.tsx",
            work_unit_id="WU-INV-09",
            scope_include=["site-vitrine/**"],
            scope_exclude=[],
            allowed_paths=["backend/**"],
        )
        == "forbidden_envelope"
    )


def test_prose_only_scope_does_not_block_envelope_product_writes() -> None:
    """Regression: prose scope labels must not make every product file out-of-scope."""
    assert (
        classify_changed_path(
            "site-vitrine/app/invest/page.tsx",
            work_unit_id="WU-INV-09",
            scope_include=["Invest public page on site-vitrine"],
            scope_exclude=[],
            allowed_paths=["site-vitrine/**"],
        )
        == "allowed_product"
    )


def test_scope_exclude_dominates_include_and_envelope() -> None:
    assert (
        classify_changed_path(
            "src/secrets/token.txt",
            work_unit_id="WU-A",
            scope_include=["src/**"],
            scope_exclude=["src/secrets/**"],
            allowed_paths=["src/**"],
        )
        == "forbidden_exclude"
    )


def test_boundary_error_aggregates_forbidden_writes() -> None:
    error = boundary_error_for_changed_files(
        [
            ".ai-team/evidence/WU-A/ok.md",
            "src/ok.py",
            ".ai-team/work-units/WU-A.yaml",
        ],
        work_unit_id="WU-A",
        wu_document={"scope": {"include": ["src/**"], "exclude": []}},
        allowed_paths=["src/**"],
    )
    assert error is not None
    message, stop = error
    assert stop == "out_of_workspace_write"
    assert "forbidden governance writes" in message
    assert ".ai-team/work-units/WU-A.yaml" in message


def test_boundary_allows_product_plus_wu_evidence() -> None:
    error = boundary_error_for_changed_files(
        [
            "src/module.py",
            ".ai-team/evidence/WU-A/ac-1.md",
            ".ai-team/runtime-results/EXE-1.json",
        ],
        work_unit_id="WU-A",
        wu_document={"scope": {"include": ["src/**"], "exclude": []}},
        allowed_paths=["src/**"],
    )
    assert error is None


def test_role_write_paths_none_does_not_constrain() -> None:
    """role_write_paths=None (the default) means the axis is not applicable —
    identical behavior to before this axis existed."""
    assert (
        classify_changed_path(
            "src/module.py",
            work_unit_id="WU-A",
            scope_include=["src/**"],
            scope_exclude=[],
            allowed_paths=["src/**"],
            role_write_paths=None,
        )
        == "allowed_product"
    )


def test_role_write_paths_rejects_out_of_role_scope_write() -> None:
    assert (
        classify_changed_path(
            "src/app.py",
            work_unit_id="WU-A",
            scope_include=["src/**"],
            scope_exclude=[],
            allowed_paths=["src/**"],
            role_write_paths=["tests/"],
        )
        == "forbidden_role_scope"
    )


def test_role_write_paths_allows_write_within_role_scope() -> None:
    assert (
        classify_changed_path(
            "tests/unit/test_app.py",
            work_unit_id="WU-A",
            scope_include=["src/**", "tests/**"],
            scope_exclude=[],
            allowed_paths=["src/**", "tests/**"],
            role_write_paths=["tests/"],
        )
        == "allowed_product"
    )


def test_role_write_paths_does_not_override_governed_output_or_exclude() -> None:
    """A role-scope axis narrower than the WU/envelope must still let governed
    outputs (evidence, runtime-results) through, and scope.exclude still wins."""
    assert (
        classify_changed_path(
            ".ai-team/evidence/WU-A/ac-1.md",
            work_unit_id="WU-A",
            scope_include=["src/**"],
            scope_exclude=[],
            allowed_paths=["src/**"],
            role_write_paths=["tests/"],
        )
        == "allowed_governed"
    )
    assert (
        classify_changed_path(
            "tests/secrets/token.txt",
            work_unit_id="WU-A",
            scope_include=["src/**", "tests/**"],
            scope_exclude=["tests/secrets/**"],
            allowed_paths=["src/**", "tests/**"],
            role_write_paths=["tests/"],
        )
        == "forbidden_exclude"
    )


def test_boundary_error_reports_out_of_role_scope_writes() -> None:
    error = boundary_error_for_changed_files(
        ["tests/unit/test_app.py", "src/app.py"],
        work_unit_id="WU-A",
        wu_document={"scope": {"include": ["src/**", "tests/**"], "exclude": []}},
        allowed_paths=["src/**", "tests/**"],
        role_write_paths=["tests/"],
    )
    assert error is not None
    message, stop = error
    assert stop == "out_of_workspace_write"
    assert "out-of-role-scope writes" in message
    assert "src/app.py" in message
    assert "tests/unit/test_app.py" not in message
