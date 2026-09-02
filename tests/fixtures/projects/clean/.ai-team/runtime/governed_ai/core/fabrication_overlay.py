"""Validate framework_source fabrication overlay (no client editor payload at repo root)."""

from __future__ import annotations

from pathlib import Path

FABRICATION_FORBIDDEN_SKILL_DIRS = frozenset(
    {
        "audit-release",
        "build-context",
        "capture-feedback",
        "challenge-requirements",
        "compile-project",
        "design-verification",
        "frontend-design",
        "impact-analysis",
        "integrate-work-units",
        "match-mandate",
        "orchestrator",
        "prepare-acceptance",
        "propose-profile",
        "verify-work-unit",
    }
)

FABRICATION_FORBIDDEN_RULE_FILES = frozenset(
    {
        "10-work-units.mdc",
        "30-permissions.mdc",
        "40-human-gates.mdc",
    }
)

EDITOR_CONFIG_DIR = "." + "cur" + "sor"
TEMPLATE_PAYLOAD_PREFIX = "adapters/cursor/templates/" + EDITOR_CONFIG_DIR + "/"


def _editor_config_root(repo_root: Path) -> Path:
    return repo_root / EDITOR_CONFIG_DIR


def collect_framework_source_fabrication_overlay_violations(repo_root: Path) -> list[str]:
    errors: list[str] = []
    editor_root = _editor_config_root(repo_root)
    if not editor_root.is_dir():
        return errors

    agents_dir = editor_root / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.md")):
            errors.append(
                "framework_source repository must not ship client subagents at "
                f"{path.relative_to(repo_root).as_posix()} "
                f"(use {TEMPLATE_PAYLOAD_PREFIX}agents/ for the install payload)"
            )

    skills_root = editor_root / "skills"
    if skills_root.is_dir():
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name in FABRICATION_FORBIDDEN_SKILL_DIRS:
                errors.append(
                    "framework_source repository must not ship client skill "
                    f"{skill_dir.relative_to(repo_root).as_posix()} "
                    f"(use {TEMPLATE_PAYLOAD_PREFIX}skills/ for the install payload)"
                )

    rules_root = editor_root / "rules"
    if rules_root.is_dir():
        for rule_name in sorted(FABRICATION_FORBIDDEN_RULE_FILES):
            path = rules_root / rule_name
            if path.is_file():
                errors.append(
                    "framework_source repository must not ship client rule "
                    f"{path.relative_to(repo_root).as_posix()} "
                    f"(use {TEMPLATE_PAYLOAD_PREFIX}rules/ for the install payload)"
                )

    return errors
