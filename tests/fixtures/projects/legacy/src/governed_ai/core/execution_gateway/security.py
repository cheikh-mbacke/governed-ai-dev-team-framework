"""Security refusals at the Agent Execution Gateway boundary."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from governed_ai.core.domain.run.path_policy import (
    CONTROL_PLANE_ONLY_PATH_PREFIXES,
    normalize_repo_path,
)
from governed_ai.core.execution_gateway.errors import ExecutionGatewayError, StructuredError

FORBIDDEN_GIT_MUTATIONS = frozenset(
    {
        "push",
        "merge",
        "rebase",
        "config",
        "remote",
    }
)

_SHELL_OPERATOR_RE = re.compile(r"(?:&&|\|\||[;&|])")
_SHELL_WRAPPERS = frozenset(
    {
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "bash",
        "bash.exe",
        "sh",
        "sh.exe",
        "git.exe",
    }
)


def _strip_quoted_regions(text: str) -> str:
    """Remove single/double-quoted spans so operators inside literals are ignored."""
    return re.sub(r"""(['"])(?:\\.|(?!\1)[^\\])*?\1""", "", text)


def _has_shell_operators(text: str) -> bool:
    return bool(_SHELL_OPERATOR_RE.search(_strip_quoted_regions(text)))


def assert_relative_workspace_path(workspace_root: Path, path: str) -> Path:
    text = str(path).replace("\\", "/").strip()
    if not text:
        raise ExecutionGatewayError(
            StructuredError(
                code="empty_path",
                message="path is empty",
                path="path",
            )
        )
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise ExecutionGatewayError(
            StructuredError(
                code="absolute_path_outside_workspace",
                message=f"absolute paths are forbidden: {path}",
                path="path",
            )
        )
    parts = Path(text).parts
    if ".." in parts:
        raise ExecutionGatewayError(
            StructuredError(
                code="forbidden_path_traversal",
                message=f"path traversal forbidden: {path}",
                path="path",
            )
        )
    absolute = (workspace_root / text).resolve()
    try:
        absolute.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ExecutionGatewayError(
            StructuredError(
                code="absolute_path_outside_workspace",
                message=f"resolved path escapes workspace: {path}",
                path="path",
            )
        ) from exc
    return absolute


def assert_not_control_plane(path: str) -> None:
    normalized = normalize_repo_path(path)
    if any(normalized.startswith(prefix) for prefix in CONTROL_PLANE_ONLY_PATH_PREFIXES):
        raise ExecutionGatewayError(
            StructuredError(
                code="forbidden_control_plane_path",
                message=f"Control Plane path mutation forbidden: {normalized}",
                path="path",
                details={"path": normalized},
            )
        )


def assert_no_escaping_link(workspace_root: Path, path: str) -> None:
    """Refuse symlinks / Windows junctions that resolve outside the workspace."""
    text = str(path).replace("\\", "/").strip()
    if ".." in Path(text).parts or text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        assert_relative_workspace_path(workspace_root, path)
        return
    absolute = workspace_root / text
    if not absolute.exists():
        return
    root = workspace_root.resolve()
    try:
        if absolute.is_symlink() or absolute.exists():
            resolved = absolute.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ExecutionGatewayError(
                    StructuredError(
                        code="escaping_symlink_or_junction",
                        message=f"symlink/junction escapes workspace: {path}",
                        path="path",
                    )
                ) from exc
    except ExecutionGatewayError:
        raise
    except OSError:
        return
    if absolute.is_symlink():
        target = os.readlink(absolute)
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = (absolute.parent / target_path).resolve()
        else:
            target_path = target_path.resolve()
        try:
            target_path.relative_to(root)
        except ValueError as exc:
            raise ExecutionGatewayError(
                StructuredError(
                    code="escaping_symlink_or_junction",
                    message=f"symlink/junction target escapes workspace: {path} -> {target}",
                    path="path",
                )
            ) from exc


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return command.split()


def assert_command_allowed(
    command: str,
    allowlist: list[str] | tuple[str, ...] | None,
    *,
    allow_empty_allowlist: bool = False,
) -> None:
    """Refuse unauthorized commands.

    An absent or empty allowlist refuses all commands unless
    ``allow_empty_allowlist`` is an explicit typed policy opt-in.
    """
    text = str(command or "").strip()
    if not text:
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message="empty command refused",
                path="command",
            )
        )
    if _has_shell_operators(text):
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message=f"shell operators are forbidden: {text}",
                path="command",
            )
        )
    tokens = _command_tokens(text)
    tool = Path(tokens[0]).name.lower() if tokens else ""
    if tool in _SHELL_WRAPPERS:
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message=f"shell/git wrapper refused: {tool}",
                path="command",
            )
        )
    lowered = text.lower()
    if lowered.startswith("git ") or tool in {"git", "git.exe"}:
        parts = tokens if tokens else lowered.split()
        verb = ""
        for part in parts[1:]:
            if part.startswith("-"):
                continue
            verb = part.lower()
            break
        if verb in FORBIDDEN_GIT_MUTATIONS:
            raise ExecutionGatewayError(
                StructuredError(
                    code="unauthorized_command",
                    message=f"git {verb} is forbidden for product agents",
                    path="command",
                )
            )
    allowed = [str(item).strip() for item in (allowlist or []) if str(item).strip()]
    if not allowed:
        if allow_empty_allowlist:
            return
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message="command allowlist is absent or empty; all commands refused",
                path="command",
            )
        )
    if text not in allowed:
        raise ExecutionGatewayError(
            StructuredError(
                code="unauthorized_command",
                message=f"command not exactly present on allowlist: {text}",
                path="command",
            )
        )


def assert_requested_commands_allowed(
    requested_commands: list[object] | None,
    allowlist: list[str] | tuple[str, ...] | None,
) -> None:
    for index, item in enumerate(requested_commands or []):
        if isinstance(item, str):
            command = item
        elif isinstance(item, dict):
            command = str(item.get("command") or item.get("argv") or "")
            if isinstance(item.get("argv"), list):
                command = " ".join(str(part) for part in item["argv"])
        else:
            raise ExecutionGatewayError(
                StructuredError(
                    code="unauthorized_command",
                    message=f"requested_commands[{index}] has unsupported type",
                    path=f"requested_commands[{index}]",
                )
            )
        assert_command_allowed(command, allowlist)


def redact_secrets(text: str, secrets: list[str] | tuple[str, ...] | None) -> str:
    redacted = text
    for secret in secrets or []:
        value = str(secret)
        if value and value in redacted:
            redacted = redacted.replace(value, "***REDACTED***")
    return redacted
