"""Cursor-specific runtime checks (hooks, CLI config, allowlist proposals)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .agent_cli import is_real_agent_launch_enabled

COMPOUND_MARKERS = ("&&", "||", ";", "|", ">", "<")
COMMAND_FIELDS = (
    "setup",
    "build",
    "lint",
    "typecheck",
    "unit_test",
    "integration_test",
    "e2e_test",
)


def platform_profile() -> str:
    if sys.platform == "win32":
        return "windows-native"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        release = platform.release().lower()
        proc_version = ""
        try:
            proc_version = Path("/proc/version").read_text(
                encoding="utf-8", errors="ignore"
            ).lower()
        except OSError:
            pass
        if os.environ.get("WSL_INTEROP") or "microsoft" in release or "microsoft" in proc_version:
            return "wsl"
        return "linux"
    return sys.platform


def _cursor_root(project_root: Path) -> Path:
    return project_root / ".cursor"


def _hook_runner(project_root: Path) -> Path:
    return _cursor_root(project_root) / "hooks" / "run_hook.cmd"


def hook_command(project_root: Path, script: Path) -> str:
    runner = _hook_runner(project_root)
    if os.name == "nt":
        return subprocess.list2cmdline([str(runner), str(script)])
    import shlex

    return f"{shlex.quote(str(runner))} {shlex.quote(str(script))}"


def probe_hook(project_root: Path, script_name: str, payload: dict[str, Any]) -> tuple[bool, str]:
    cursor = _cursor_root(project_root)
    runner = _hook_runner(project_root)
    script = cursor / "hooks" / script_name
    if not runner.is_file():
        return False, f"missing {runner.relative_to(project_root)}"
    if not script.is_file():
        return False, f"missing {script.relative_to(project_root)}"
    try:
        result = subprocess.run(
            hook_command(project_root, script),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=project_root,
            shell=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        return False, detail
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, f"invalid hook JSON: {result.stdout.strip()!r}"
    if response.get("permission") != "allow":
        return False, f"unexpected response: {response!r}"
    return True, "permission=allow"


def check_project_cli(project_root: Path) -> tuple[bool, str]:
    path = _cursor_root(project_root) / "cli.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, str(exc)
    unsupported = sorted(set(config) - {"permissions"})
    if unsupported:
        return False, "global-only project keys: " + ", ".join(unsupported)
    permissions = config.get("permissions")
    if not isinstance(permissions, dict):
        return False, "permissions must be an object"
    entries = list(permissions.get("allow") or []) + list(permissions.get("deny") or [])
    if any("whoami" in str(entry).lower() for entry in entries):
        return False, "Shell(whoami) is already present in project permissions"
    return True, "project permissions valid; whoami is not pre-authorized"


def check_hooks_config(project_root: Path) -> tuple[bool, str]:
    path = _cursor_root(project_root) / "hooks.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, str(exc)
    commands = [
        item.get("command", "")
        for definitions in config.get("hooks", {}).values()
        for item in definitions
        if isinstance(item, dict)
    ]
    if not commands:
        return False, "no hook commands configured"
    expected_prefix = ".cursor/hooks/run_hook.cmd "
    direct_python = [command for command in commands if not command.startswith(expected_prefix)]
    if direct_python:
        return False, "hooks bypass the portable runner: " + ", ".join(direct_python)
    return True, f"{len(commands)} hook commands use the portable runner"


def collect_preflight_report(
    project_root: Path,
    *,
    unattended: bool = False,
) -> dict[str, Any]:
    profile = platform_profile()
    hook_config_ok, hook_config_detail = check_hooks_config(project_root)
    cli_ok, cli_detail = check_project_cli(project_root)
    guard_ok, guard_detail = probe_hook(project_root, "guard_shell.py", {"command": "whoami"})
    agent_path = shutil.which("agent")
    readonly = (
        {
            "status": "skip",
            "detail": (
                "Cursor workspace_readonly unavailable on native Windows; use WSL/Linux"
            ),
        }
        if profile == "windows-native"
        else {
            "status": "expected",
            "detail": "run the architect integration smoke to verify this host",
        }
    )
    report: dict[str, Any] = {
        "platform": profile,
        "python": {"status": "pass", "detail": sys.executable},
        "cursor_agent": {
            "status": "pass" if agent_path else "fail",
            "detail": agent_path or "agent not found on PATH",
        },
        "hooks_config": {
            "status": "pass" if hook_config_ok else "fail",
            "detail": hook_config_detail,
        },
        "guard_hook": {
            "status": "pass" if guard_ok else "fail",
            "detail": guard_detail,
        },
        "project_cli": {"status": "pass" if cli_ok else "fail", "detail": cli_detail},
        "global_allowlist": {
            "status": "manual",
            "detail": "confirm Approval mode=Allowlist and Shell(whoami) absent in /config",
        },
        "execution_surface": {
            "status": "manual",
            "detail": "run the authorization smoke from agent --workspace, not IDE Agent chat",
        },
        "readonly_sandbox": readonly,
        "allowlist_smoke": {
            "status": (
                "ready" if hook_config_ok and cli_ok and guard_ok and agent_path else "blocked"
            ),
            "detail": (
                "use auth-smoke; this does not replace the architect readonly integration smoke"
            ),
        },
    }
    if unattended:
        launch_enabled = is_real_agent_launch_enabled()
        report["real_agent_launch"] = {
            "status": "pass" if launch_enabled else "fail",
            "detail": (
                "native Cursor agent execution explicitly enabled"
                if launch_enabled
                else "set GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH=1 before unattended preflight"
            ),
        }
        # Document 6 §9.6 — manual confirmation states forbid unattended start.
        # A human may attest those Cursor-UI-only checks via env so the report
        # can back OpenRun without inventing a Core bypass.
        acknowledged = os.environ.get("GOVERNED_AI_ACKNOWLEDGE_MANUAL_PREFLIGHT") == "1"
        for name in ("global_allowlist", "execution_surface"):
            entry = report.get(name)
            if not isinstance(entry, dict) or entry.get("status") != "manual":
                continue
            if acknowledged:
                report[name] = {
                    "status": "pass",
                    "detail": (
                        f"{entry.get('detail')} "
                        "(human-attested via GOVERNED_AI_ACKNOWLEDGE_MANUAL_PREFLIGHT=1)"
                    ),
                }
            else:
                report[name] = {
                    "status": "manual",
                    "detail": (
                        f"{entry.get('detail')} — set "
                        "GOVERNED_AI_ACKNOWLEDGE_MANUAL_PREFLIGHT=1 after confirming, "
                        "or OpenRun will refuse this check"
                    ),
                }
    return report


def last_hook_activity(project_root: Path) -> dict[str, Any] | None:
    log_path = project_root / ".ai-team" / "logs" / "cursor-events.jsonl"
    if not log_path.is_file():
        return None
    last_line = None
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                last_line = stripped
    if not last_line:
        return None
    try:
        record = json.loads(last_line)
    except json.JSONDecodeError:
        return {"parse_error": True}
    return record if isinstance(record, dict) else None


def load_cursor_json(project_root: Path, relative: str) -> dict[str, Any] | None:
    path = project_root / relative
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_compound(command: str) -> bool:
    return any(marker in command for marker in COMPOUND_MARKERS)


def cli_token(command: str) -> str:
    tool, _, rest = command.partition(" ")
    rest = rest.strip()
    return f"Shell({tool}:{rest}*)" if rest else f"Shell({tool}:*)"


def build_allowlist_proposals(
    declared_commands: dict[str, str],
    ui_config: dict[str, Any],
    cli_config: dict[str, Any],
) -> list[dict[str, Any]]:
    existing_terminal = set(ui_config.get("terminalAllowlist") or [])
    existing_cli_allow = set((cli_config.get("permissions") or {}).get("allow") or [])

    proposals: list[dict[str, Any]] = []
    seen_commands: set[str] = set()
    for field, command in declared_commands.items():
        if command in seen_commands:
            continue
        seen_commands.add(command)
        entry: dict[str, Any] = {
            "source_field": field,
            "command": command,
            "terminal_allowlist_entry": command,
            "terminal_allowlist_already_present": command in existing_terminal,
        }
        if is_compound(command):
            entry["cli_allow_token"] = None
            entry["cli_allow_already_present"] = False
            entry["cli_allow_note"] = (
                "compound command (shell operator present) - author the Shell() "
                "token(s) yourself, one per stage if needed"
            )
        else:
            token = cli_token(command)
            entry["cli_allow_token"] = token
            entry["cli_allow_already_present"] = token in existing_cli_allow
        proposals.append(entry)
    return proposals
