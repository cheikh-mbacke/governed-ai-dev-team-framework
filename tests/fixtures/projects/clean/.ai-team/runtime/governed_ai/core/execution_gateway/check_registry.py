"""Canonical governed check registry with bounded, unambiguous aliases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError

CheckCategory = Literal[
    "implementation",
    "verification",
    "review",
    "security",
    "audit",
    "integration",
    "acceptance",
]


@dataclass(frozen=True, slots=True)
class CheckDefinition:
    canonical_id: str
    aliases: frozenset[str]
    category: CheckCategory
    authorized_roles: frozenset[str]
    procedures: frozenset[str]
    evidence_type: str
    blocking: bool
    independent_verification: str | None = None


# Explicit aliases only — no substring guessing, no shared aliases across checks.
_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        canonical_id="implementation",
        aliases=frozenset({"implementation", "implement", "impl"}),
        category="implementation",
        authorized_roles=frozenset({"backend-developer", "frontend-developer"}),
        procedures=frozenset(
            {
                "implement-work-unit",
                "implement-approved-design",
                "adapt-approved-design",
                "frontend-design",
                "create-frontend-design",
            }
        ),
        evidence_type="diff_and_artifact",
        blocking=True,
        independent_verification="diff_scope",
    ),
    CheckDefinition(
        canonical_id="tests",
        aliases=frozenset(
            {
                "tests",
                "test",
                "pytest",
                "unit-tests",
                "unit_tests",
                "mvn-test",
                "mvn-test-failsafe",
                "mvn_test_failsafe",
                "qa",
                "webapp-testing",
            }
        ),
        category="verification",
        authorized_roles=frozenset({"qa-test"}),
        procedures=frozenset({"webapp-testing", "design-verification"}),
        evidence_type="command_transcript",
        blocking=True,
        independent_verification="unit_test",
    ),
    CheckDefinition(
        canonical_id="code_review",
        aliases=frozenset(
            {
                "code_review",
                "code-review",
                "codereview",
                "review",
                "code review",
            }
        ),
        category="review",
        authorized_roles=frozenset({"code-reviewer"}),
        procedures=frozenset({"webapp-testing", "challenge-requirements"}),
        evidence_type="review_report",
        blocking=True,
    ),
    CheckDefinition(
        canonical_id="security_review",
        aliases=frozenset(
            {
                "security_review",
                "security-review",
                "security review",
            }
        ),
        category="security",
        authorized_roles=frozenset({"security-reviewer"}),
        procedures=frozenset({"security-review"}),
        evidence_type="security_report",
        blocking=True,
    ),
    CheckDefinition(
        canonical_id="audit",
        aliases=frozenset(
            {
                "audit",
                "audit_release",
                "audit-release",
                "audit release",
            }
        ),
        category="audit",
        authorized_roles=frozenset({"auditor"}),
        procedures=frozenset({"audit-release"}),
        evidence_type="audit_report",
        blocking=True,
    ),
    CheckDefinition(
        canonical_id="integration_review",
        aliases=frozenset(
            {
                "integration_review",
                "integration-review",
                "integration review",
            }
        ),
        category="integration",
        authorized_roles=frozenset({"integration-steward"}),
        procedures=frozenset({"integrate-work-units"}),
        evidence_type="integration_report",
        blocking=True,
    ),
    CheckDefinition(
        canonical_id="lint",
        aliases=frozenset({"lint", "linter", "ruff", "eslint"}),
        category="verification",
        authorized_roles=frozenset({"backend-developer", "frontend-developer", "qa-test"}),
        procedures=frozenset({"implement-work-unit", "webapp-testing"}),
        evidence_type="command_transcript",
        blocking=True,
        independent_verification="lint",
    ),
    CheckDefinition(
        canonical_id="build",
        aliases=frozenset({"build", "compile"}),
        category="verification",
        authorized_roles=frozenset({"backend-developer", "frontend-developer", "qa-test"}),
        procedures=frozenset({"implement-work-unit", "webapp-testing"}),
        evidence_type="command_transcript",
        blocking=True,
        independent_verification="build",
    ),
)

_BY_CANONICAL: dict[str, CheckDefinition] = {item.canonical_id: item for item in _CHECKS}


def _normalize_token(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _build_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for definition in _CHECKS:
        for alias in definition.aliases:
            token = _normalize_token(alias)
            if not token:
                continue
            existing = mapping.get(token)
            if existing is not None and existing != definition.canonical_id:
                raise RuntimeError(
                    f"ambiguous check alias {alias!r}: {existing} vs {definition.canonical_id}"
                )
            mapping[token] = definition.canonical_id
    return mapping


_ALIAS_TO_CANONICAL = _build_alias_map()

_AC_ID_RE = re.compile(r"^AC-[A-Za-z0-9][A-Za-z0-9._-]*(?:-\d+\.\.\d+)?(?:\b|$)")
_AC_RANGE_RE = re.compile(r"^(AC-.+-)(\d+)\.\.(\d+)(?:\D|$)")


def list_checks() -> tuple[CheckDefinition, ...]:
    return _CHECKS


def get_check(canonical_id: str) -> CheckDefinition | None:
    return _BY_CANONICAL.get(canonical_id)


def normalize_check_name(name: str) -> str | None:
    """Return canonical_id for a known check/alias, or None if unknown.

    Acceptance-criterion identifiers (``AC-*``, including descriptive suffixes
    and compact ranges ``AC-…-01..05``) normalize to themselves when syntactically
    valid — they are not aliases of another check.
    """
    raw = str(name or "").strip()
    if not raw:
        return None
    # Descriptive AC: "AC-WU-01 first scenario" → keep leading AC id.
    ac_match = re.match(r"^(AC-[A-Za-z0-9][A-Za-z0-9._-]*)", raw)
    if ac_match:
        return ac_match.group(1)
    token = _normalize_token(raw)
    return _ALIAS_TO_CANONICAL.get(token)


def expand_ac_ranges(names: set[str]) -> set[str]:
    expanded: set[str] = set()
    for name in names:
        match = _AC_RANGE_RE.match(name)
        if not match:
            continue
        prefix, start_text, end_text = match.groups()
        start, end = int(start_text), int(end_text)
        if end < start or end - start > 100:
            continue
        width = max(len(start_text), len(end_text))
        expanded.update(f"{prefix}{index:0{width}d}" for index in range(start, end + 1))
    return expanded


def resolve_required_checks(
    reported_names: list[str] | set[str],
    *,
    required: list[str] | tuple[str, ...],
) -> tuple[set[str], list[str], list[str]]:
    """Map reported names to canonical ids.

    Returns ``(satisfied_canonical, unknown_or_ambiguous, missing_required)``.
    An unknown/ambiguous name never satisfies a required check.
    """
    satisfied: set[str] = set()
    rejected: list[str] = []
    for raw in reported_names:
        canonical = normalize_check_name(str(raw))
        if canonical is None:
            rejected.append(str(raw))
            continue
        satisfied.add(canonical)
        # Range expansion contributes concrete AC ids.
        satisfied.update(expand_ac_ranges({canonical}))

    missing = [
        item
        for item in required
        if item not in satisfied
        and not (
            item.startswith("AC-")
            and any(
                name == item
                or (name.startswith(item) and name[len(item) : len(item) + 1] in " :_-./")
                for name in satisfied
            )
        )
    ]
    return satisfied, rejected, missing


def require_unique_alias(alias: str) -> str:
    canonical = normalize_check_name(alias)
    if canonical is None:
        raise ExecutionGatewayError(
            StructuredError(
                code="unknown_check_alias",
                message=f"check alias {alias!r} is not registered",
                path="checks",
            )
        )
    return canonical


def assert_check_authorized(
    *,
    canonical_id: str,
    role_id: str,
    procedure_id: str,
    evidence_type: str | None = None,
) -> CheckDefinition:
    definition = get_check(canonical_id)
    if definition is None:
        # AC-* ids are free-form acceptance criteria — no registry role gate.
        if canonical_id.startswith("AC-"):
            return CheckDefinition(
                canonical_id=canonical_id,
                aliases=frozenset({canonical_id}),
                category="acceptance",
                authorized_roles=frozenset({role_id}),
                procedures=frozenset({procedure_id}),
                evidence_type=evidence_type or "acceptance",
                blocking=True,
            )
        raise ExecutionGatewayError(
            StructuredError(
                code="unknown_check_alias",
                message=f"check {canonical_id!r} is not registered",
                path="checks",
            )
        )
    if role_id not in definition.authorized_roles:
        raise ExecutionGatewayError(
            StructuredError(
                code="check_role_unauthorized",
                message=(
                    f"role {role_id!r} is not authorized for check {canonical_id!r}"
                ),
                path="checks",
            )
        )
    if definition.procedures and procedure_id not in definition.procedures:
        raise ExecutionGatewayError(
            StructuredError(
                code="check_procedure_mismatch",
                message=(
                    f"procedure {procedure_id!r} cannot satisfy check {canonical_id!r}"
                ),
                path="checks",
            )
        )
    if evidence_type and evidence_type != definition.evidence_type:
        raise ExecutionGatewayError(
            StructuredError(
                code="check_evidence_type_mismatch",
                message=(
                    f"evidence type {evidence_type!r} does not match registry "
                    f"{definition.evidence_type!r} for {canonical_id}"
                ),
                path="checks",
            )
        )
    return definition


def registry_blocking(canonical_id: str, *, fallback: bool = True) -> bool:
    definition = get_check(canonical_id)
    if definition is None:
        return fallback
    return definition.blocking
