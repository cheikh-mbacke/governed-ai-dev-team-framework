"""Claude-Code-specific runtime checks (binary presence, settings.json, hooks).

Deliberately smaller than adapters/cursor/runtime/checks.py: Cursor's
`global_allowlist`/`execution_surface`/`readonly_sandbox`/`allowlist_smoke`
checks and its unattended-preflight-attestation machinery encode Cursor-UI-
specific manual-approval concepts (its own "Approval mode" surface) with no
verified Claude Code equivalent — inventing one here would be guessing, not
porting. `scripts/ai-team/preflight.py` is not wired to this module yet
(that CLI entry point's installed-layout adapter aliasing — see
`install_paths._ensure_adapters_cursor_alias` — has only been verified for
Cursor); this module is usable standalone in the meantime.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from governed_ai.adapters.common.agent_invocation import is_real_agent_launch_enabled
from governed_ai.adapters.common.platform import platform_profile

__all__ = ["collect_preflight_report", "platform_profile", "probe_hook"]


def _claude_dir(project_root: Path) -> Path:
    return project_root / ".claude"


def _hook_runner(project_root: Path) -> Path:
    return _claude_dir(project_root) / "hooks" / "run_hook.cmd"


def _posix_shell() -> str:
    return "/bin/sh" if Path("/bin/sh").is_file() else "sh"


def hook_command(project_root: Path, script: Path) -> str:
    """Build a shell command line invoking the portable run_hook.cmd runner.

    Mirrors adapters/cursor/runtime/checks.py::hook_command exactly — the
    cross-platform quoting (list2cmdline on Windows, sh -c elsewhere) has
    nothing Cursor-specific about it.
    """
    runner = _hook_runner(project_root)
    if os.name == "nt":
        return subprocess.list2cmdline([str(runner), str(script)])
    import shlex

    runner_rel = runner.relative_to(project_root).as_posix()
    script_rel = script.relative_to(project_root).as_posix()
    return f"{_posix_shell()} {shlex.quote(runner_rel)} {shlex.quote(script_rel)}"


def probe_hook(project_root: Path, script_name: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """Run a named hook script with JSON stdin; True/detail on the process exit code.

    Unlike Cursor's probe (which expects a JSON {"permission": ...} reply on
    every hook), Claude Code hooks signal via exit code — 0 allows, 2 blocks
    (verified, see adapters/claude_code/templates/.claude/hooks/guard_shell.py)
    — so this reports on exit code, treating any JSON body as informational.
    """
    runner = _hook_runner(project_root)
    script = _claude_dir(project_root) / "hooks" / script_name
    if not runner.is_file():
        return False, f"missing {runner.relative_to(project_root)}"
    if not script.is_file():
        return False, f"hook script missing: {script_name}"
    try:
        result = subprocess.run(
            hook_command(project_root, script),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=project_root,
            shell=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"hook invocation failed: {exc}"
    if result.returncode not in (0, 2):
        return False, f"unexpected exit code {result.returncode}: {result.stderr.strip()[:200]}"
    return True, f"exit code {result.returncode}"


def check_claude_binary() -> tuple[str, str]:
    binary = shutil.which("claude")
    if binary is None:
        return "fail", "claude CLI not found on PATH"
    return "pass", binary


def check_settings_config(project_root: Path) -> tuple[str, str]:
    settings_path = _claude_dir(project_root) / "settings.json"
    if not settings_path.is_file():
        return "fail", f"missing {settings_path.relative_to(project_root).as_posix()}"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return "fail", f"invalid JSON: {exc}"
    if not isinstance(data.get("permissions"), dict):
        return "fail", "settings.json missing a permissions object"
    return "pass", "settings.json present and parses"


def check_guard_hook(project_root: Path) -> tuple[str, str]:
    if sys.platform != "win32" and shutil.which("python3") is None and shutil.which("python") is None:
        return "skip", "no python interpreter on PATH for run_hook.cmd to launch"
    ok, detail = probe_hook(
        project_root,
        "guard_shell.py",
        {"tool_name": "Bash", "tool_input": {"command": "git status"}},
    )
    return ("pass" if ok else "fail"), detail


def collect_preflight_report(project_root: Path, *, unattended: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {"platform": platform_profile()}

    binary_status, binary_detail = check_claude_binary()
    report["claude_binary"] = {"status": binary_status, "detail": binary_detail}

    settings_status, settings_detail = check_settings_config(project_root)
    report["settings_config"] = {"status": settings_status, "detail": settings_detail}

    if (_claude_dir(project_root) / "hooks" / "guard_shell.py").is_file():
        guard_status, guard_detail = check_guard_hook(project_root)
    else:
        guard_status, guard_detail = "skip", "guard_shell.py not installed"
    report["guard_hook"] = {"status": guard_status, "detail": guard_detail}

    if unattended:
        report["real_agent_launch"] = {
            "status": "pass" if is_real_agent_launch_enabled() else "not_enabled",
            "detail": "GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH",
        }

    return report
