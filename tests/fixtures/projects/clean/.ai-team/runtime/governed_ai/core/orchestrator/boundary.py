"""Classify implementation writes against scope, envelope, and governed outputs.

Product paths must satisfy path-like ``scope.include`` and, when present, the
grant ``allowed_paths``. Governance outputs for the active Work Unit are
allowed on a narrow allowlist. Protected governance paths and ``scope.exclude``
always dominate.
"""

from __future__ import annotations

import fnmatch
from typing import Any

from governed_ai.core.domain.run.path_policy import (
    CONTROL_PLANE_ONLY_PATH_PREFIXES,
    normalize_repo_path,
)


def path_is_allowed(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    normalized = normalize_repo_path(path)
    for raw_pattern in patterns:
        pattern = normalize_repo_path(raw_pattern)
        if not pattern:
            continue
        if pattern.endswith("/") and normalized.startswith(pattern):
            return True
        if fnmatch.fnmatchcase(normalized, pattern):
            return True
    return False


def is_path_scope_pattern(pattern: str) -> bool:
    """Return True when a scope entry is a path/glob, not free-form prose."""
    text = pattern.replace("\\", "/").strip()
    if not text:
        return False
    if " " in text and not any(ch in text for ch in "*?[]"):
        return False
    if any(ch in text for ch in "\\/*?[]"):
        return True
    if text.startswith("."):
        return True
    if "." in text.rsplit("/", 1)[-1]:
        return True
    # Single token: treat lowercase path-ish tokens as globs ("src"), not titles.
    return text == text.lower()


def path_scope_patterns(entries: list[str] | tuple[str, ...] | None) -> list[str]:
    return [str(item) for item in (entries or []) if is_path_scope_pattern(str(item))]


def governed_output_patterns(work_unit_id: str) -> list[str]:
    wu = work_unit_id.strip()
    return [
        f".ai-team/evidence/{wu}/**",
        f".ai-team/evidence/{wu}/*",
        f".ai-team/evidence/{wu}/",
        ".ai-team/runtime-results/**",
        ".ai-team/runtime-results/*",
    ]


def is_forbidden_governance_mutation(path: str) -> bool:
    normalized = normalize_repo_path(path)
    return any(normalized.startswith(prefix) for prefix in CONTROL_PLANE_ONLY_PATH_PREFIXES)


def is_governed_output(path: str, *, work_unit_id: str) -> bool:
    return path_is_allowed(path, governed_output_patterns(work_unit_id))


def classify_changed_path(
    path: str,
    *,
    work_unit_id: str,
    scope_include: list[str] | tuple[str, ...] | None,
    scope_exclude: list[str] | tuple[str, ...] | None,
    allowed_paths: list[str] | tuple[str, ...] | None,
    role_write_paths: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Return a classification token for one changed path.

    ``role_write_paths`` is the resolved (see
    ``execution_gateway.scope.resolve_role_write_paths``) form of the acting
    role's ``writes.product.paths`` — ``None`` means the axis does not apply
    (readonly role, or a placeholder that could not be resolved yet), not
    "allow nothing".
    """
    include = path_scope_patterns(scope_include)
    exclude = path_scope_patterns(scope_exclude)
    envelope = [str(item) for item in (allowed_paths or []) if str(item).strip()]
    role_scope = (
        [str(item) for item in role_write_paths if str(item).strip()]
        if role_write_paths is not None
        else None
    )

    if is_forbidden_governance_mutation(path):
        return "forbidden_governance"
    if exclude and path_is_allowed(path, exclude):
        return "forbidden_exclude"
    if is_governed_output(path, work_unit_id=work_unit_id):
        return "allowed_governed"
    if include and not path_is_allowed(path, include):
        return "forbidden_scope"
    if envelope and not path_is_allowed(path, envelope):
        return "forbidden_envelope"
    if role_scope is not None and not path_is_allowed(path, role_scope):
        return "forbidden_role_scope"
    return "allowed_product"


def boundary_error_for_changed_files(
    files: list[str],
    *,
    work_unit_id: str,
    wu_document: dict[str, Any],
    allowed_paths: list[str],
    role_write_paths: list[str] | None = None,
) -> tuple[str, str | None] | None:
    """Return (message, global_stop_condition) when writes violate the boundary."""
    scope = wu_document.get("scope") or {}
    scope_include = scope.get("include") or []
    scope_exclude = scope.get("exclude") or []

    forbidden_governance: list[str] = []
    forbidden_exclude: list[str] = []
    forbidden_scope: list[str] = []
    forbidden_envelope: list[str] = []
    forbidden_role_scope: list[str] = []

    for path in files:
        kind = classify_changed_path(
            path,
            work_unit_id=work_unit_id,
            scope_include=scope_include,
            scope_exclude=scope_exclude,
            allowed_paths=allowed_paths,
            role_write_paths=role_write_paths,
        )
        if kind == "forbidden_governance":
            forbidden_governance.append(path)
        elif kind == "forbidden_exclude":
            forbidden_exclude.append(path)
        elif kind == "forbidden_scope":
            forbidden_scope.append(path)
        elif kind == "forbidden_envelope":
            forbidden_envelope.append(path)
        elif kind == "forbidden_role_scope":
            forbidden_role_scope.append(path)

    if forbidden_governance:
        return (
            f"forbidden governance writes detected: {forbidden_governance}",
            "out_of_workspace_write",
        )
    if forbidden_exclude:
        return (
            f"scope.exclude writes detected: {forbidden_exclude}",
            "out_of_workspace_write",
        )
    if forbidden_scope:
        return f"out-of-scope writes detected: {forbidden_scope}", "out_of_workspace_write"
    if forbidden_envelope:
        return (
            f"out-of-envelope writes detected: {forbidden_envelope}",
            "out_of_workspace_write",
        )
    if forbidden_role_scope:
        return (
            f"out-of-role-scope writes detected: {forbidden_role_scope}",
            "out_of_workspace_write",
        )
    return None
