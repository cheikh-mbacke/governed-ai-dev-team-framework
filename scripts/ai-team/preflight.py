#!/usr/bin/env python3
"""Dependency-free preflight for Cursor UI/CLI governance hooks.

This checks deterministic local prerequisites. Cursor's global Approval mode
and the visibility of an interactive prompt remain human checks because project
configuration cannot read or set them.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


from i18n import project_language, t

ROOT = Path(__file__).resolve().parents[2]
CURSOR = ROOT / ".cursor"
HOOK_RUNNER = CURSOR / "hooks" / "run_hook.cmd"
LANG = project_language(ROOT)


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


def hook_command(script: Path) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([str(HOOK_RUNNER), str(script)])
    import shlex

    return f"{shlex.quote(str(HOOK_RUNNER))} {shlex.quote(str(script))}"


def probe_hook(script_name: str, payload: dict) -> tuple[bool, str]:
    script = CURSOR / "hooks" / script_name
    if not HOOK_RUNNER.is_file():
        return False, f"missing {HOOK_RUNNER.relative_to(ROOT)}"
    if not script.is_file():
        return False, f"missing {script.relative_to(ROOT)}"
    try:
        result = subprocess.run(
            hook_command(script),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=ROOT,
            shell=True,
            timeout=10,
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


def check_project_cli() -> tuple[bool, str]:
    path = CURSOR / "cli.json"
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


def check_hooks_config() -> tuple[bool, str]:
    path = CURSOR / "hooks.json"
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


def collect_report() -> dict:
    profile = platform_profile()
    hook_config_ok, hook_config_detail = check_hooks_config()
    cli_ok, cli_detail = check_project_cli()
    guard_ok, guard_detail = probe_hook("guard_shell.py", {"command": "whoami"})
    agent_path = shutil.which("agent")
    readonly = (
        {
            "status": "skip",
            "detail": (
                "Cursor workspace_readonly unavailable on native Windows; "
                "use WSL/Linux"
            ),
        }
        if profile == "windows-native"
        else {
            "status": "expected",
            "detail": "run the architect integration smoke to verify this host",
        }
    )
    return {
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
                "use auth-smoke; this does not replace the architect readonly "
                "integration smoke"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Cursor CLI governance prerequisites")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = collect_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        # Field names/statuses below stay in English even in a French
        # project: they are the technical contract other tooling and docs
        # (auth-smoke, TERMINAL_GUIDE) reference verbatim - see i18n.py.
        print(t(LANG, "Governed AI Team preflight", "Verification prealable Governed AI Team"))
        print("=" * 26)
        print(f"platform: {report['platform']}")
        for name, result in report.items():
            if name == "platform":
                continue
            print(f"{result['status'].upper():8} {name}: {result['detail']}")
    blocking = {"fail", "blocked"}
    return 1 if any(
        isinstance(result, dict) and result.get("status") in blocking
        for result in report.values()
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
