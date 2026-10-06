"""POSIX hook commands must not depend on the executable bit of run_hook.cmd."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.cursor.runtime.checks import (
    check_hooks_config,
    prefix_posix_hook_command,
    rewrite_installed_hooks,
)


def test_prefix_posix_hook_command_adds_sh() -> None:
    bare = ".cursor/hooks/run_hook.cmd .cursor/hooks/guard_shell.py"
    assert prefix_posix_hook_command(bare) == f"sh {bare}"
    assert prefix_posix_hook_command(f"sh {bare}") == f"sh {bare}"


def test_check_hooks_config_accepts_sh_prefix(tmp_path: Path) -> None:
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    (cursor / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "beforeShellExecution": [
                        {
                            "command": (
                                "sh .cursor/hooks/run_hook.cmd "
                                ".cursor/hooks/guard_shell.py"
                            )
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    ok, detail = check_hooks_config(tmp_path)
    assert ok, detail


def test_rewrite_installed_hooks_on_posix(tmp_path: Path) -> None:
    path = tmp_path / "hooks.json"
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "sessionStart": [
                        {"command": ".cursor/hooks/run_hook.cmd .cursor/hooks/session_init.py"}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    rewrite_installed_hooks(path, posix=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    command = config["hooks"]["sessionStart"][0]["command"]
    assert command.startswith("sh .cursor/hooks/run_hook.cmd ")
