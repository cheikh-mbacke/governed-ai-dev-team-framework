"""Distinguish framework source repositories from installed client workspaces."""

from __future__ import annotations

from pathlib import Path

from governed_ai.core.workspace import Workspace

FRAMEWORK_SOURCE_KIND = "framework_source"
FEEDBACK_REFERENCE_FIXTURE = "tests/fixtures/projects/clean/"

FEEDBACK_FORBIDDEN_MESSAGE = (
    "Feedback commands are not allowed on a framework_source repository. "
    "This directory builds the framework; use an installed target project or "
    f"{FEEDBACK_REFERENCE_FIXTURE} to exercise the feedback loop."
)

CLIENT_CYCLE_FORBIDDEN_MESSAGE = (
    "Client governance commands are not available on a framework_source repository. "
    "This directory builds the framework. See AGENTS.md for the fabrication workflow, "
    f"or {FEEDBACK_REFERENCE_FIXTURE} to exercise installed-client behavior."
)

CLIENT_CYCLE_DIRECTORIES = (
    "work-units",
    "events",
    "evidence",
    "decisions",
    "context-packages",
    "acceptance",
    "authorizations",
    "releases",
)


def read_repository_kind(root: Path) -> str | None:
    for profile in (
        root / ".fabric" / "project-profile.yaml",
        root / ".ai-team" / "project-profile.yaml",
    ):
        if not profile.is_file():
            continue
        for line in profile.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("repository_kind:"):
                return stripped.split(":", 1)[1].strip()
    return None


def is_framework_source(workspace: Workspace | Path) -> bool:
    root = workspace.root if isinstance(workspace, Workspace) else Path(workspace).resolve()
    return read_repository_kind(root) == FRAMEWORK_SOURCE_KIND


def ensure_feedback_allowed(workspace: Workspace) -> None:
    if is_framework_source(workspace):
        from governed_ai.core.commands.errors import ErrorCode, GatewayError

        raise GatewayError(
            ErrorCode.UNSUPPORTED_CONTRACT,
            FEEDBACK_FORBIDDEN_MESSAGE,
            "/workspace",
        )


def ensure_client_cycle_allowed(workspace: Workspace) -> None:
    if is_framework_source(workspace):
        from governed_ai.core.commands.errors import ErrorCode, GatewayError

        raise GatewayError(
            ErrorCode.UNSUPPORTED_CONTRACT,
            CLIENT_CYCLE_FORBIDDEN_MESSAGE,
            "/workspace",
        )


def collect_framework_source_root_layout_violations(root: Path) -> list[str]:
    errors: list[str] = []
    if (root / ".ai-team").exists():
        errors.append(
            "framework_source repository must not contain a root .ai-team/ directory; "
            "use .fabric/ for fabrication metadata and distribution/payload/.ai-team/ "
            "for the installable payload"
        )
    fabric_profile = root / ".fabric" / "project-profile.yaml"
    if not fabric_profile.is_file():
        errors.append(
            "framework_source repository must declare .fabric/project-profile.yaml"
        )
    return errors


def collect_framework_source_feedback_artifacts(ai_team: Path) -> list[str]:
    errors: list[str] = []
    for pattern, label in (
        ("observations/OBS-*.yaml", "observation"),
        ("retrospectives/RET-*.yaml", "retrospective"),
        ("metrics/framework-feedback-*.json", "feedback export"),
    ):
        for path in sorted(ai_team.glob(pattern)):
            errors.append(
                f"framework_source repository must not contain client feedback {label} "
                f"({path.relative_to(ai_team.parent).as_posix()})"
            )
    return errors


def collect_framework_source_client_cycle_artifacts(
    ai_team: Path, *, state: dict | None = None
) -> list[str]:
    errors: list[str] = []
    if state is not None:
        if state.get("phase") != "not_compiled":
            errors.append(
                "framework_source repository seed project-state.yaml phase must be "
                f"'not_compiled' (found {state.get('phase')!r})"
            )
        if state.get("work_units"):
            errors.append(
                "framework_source repository seed project-state.yaml work_units must be empty"
            )
        for field in ("milestones", "increments", "releases", "critical_path"):
            if state.get(field):
                errors.append(
                    f"framework_source repository seed project-state.yaml must not define {field}"
                )

    for directory in CLIENT_CYCLE_DIRECTORIES:
        for path in sorted((ai_team / directory).glob("*.yaml")):
            errors.append(
                "framework_source repository must not contain client-cycle artifacts "
                f"({path.relative_to(ai_team.parent).as_posix()})"
            )
        for path in sorted((ai_team / directory).glob("*.json")):
            if path.name == ".gitkeep":
                continue
            errors.append(
                "framework_source repository must not contain client-cycle artifacts "
                f"({path.relative_to(ai_team.parent).as_posix()})"
            )
    return errors
