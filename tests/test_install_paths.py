"""Installed-layout import portability for scripts/ai-team/install_paths.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLEAN_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "projects" / "clean"
SOURCE_INSTALL_PATHS = REPO_ROOT / "scripts" / "ai-team" / "install_paths.py"
INSTALL = REPO_ROOT / "tools" / "install.py"


def _run_python(cwd: Path, script: str, *, extra_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    preamble = ""
    if extra_path is not None:
        preamble = f"import sys\nsys.path.insert(0, {str(extra_path)!r})\n"
    return subprocess.run(
        [sys.executable, "-c", preamble + script],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def test_clean_fixture_has_no_top_level_adapters_package() -> None:
    assert not (CLEAN_FIXTURE / "adapters").exists()
    assert (CLEAN_FIXTURE / ".ai-team" / "runtime" / "governed_ai").is_dir()


def test_bootstrap_aliases_adapters_cursor_on_clean_fixture() -> None:
    """Source install_paths against frozen clean runtime (no top-level adapters/)."""
    result = _run_python(
        CLEAN_FIXTURE,
        """
from pathlib import Path
from install_paths import bootstrap_runtime, import_adapters_cursor

root = Path('.').resolve()
assert not (root / 'adapters').exists()
bootstrap_runtime(root)
agent_cli = import_adapters_cursor('runtime.agent_cli')
assert hasattr(agent_cli, 'is_real_agent_launch_enabled')
from adapters.cursor.runtime.agent_cli import is_real_agent_launch_enabled
assert is_real_agent_launch_enabled is agent_cli.is_real_agent_launch_enabled
from governed_ai.adapters.cursor.adapter import CursorAdapter
assert CursorAdapter is not None
print('OK')
""",
        extra_path=SOURCE_INSTALL_PATHS.parent,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_fresh_install_imports_cursor_adapter_without_top_level_adapters(
    tmp_path: Path,
) -> None:
    target = tmp_path / "installed"
    install = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "portability-smoke",
            "--project-name",
            "Portability Smoke",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    assert not (target / "adapters").exists()
    assert (target / "scripts" / "ai-team" / "install_paths.py").is_file()

    result = _run_python(
        target,
        """
from pathlib import Path
import sys
sys.path.insert(0, str(Path('scripts/ai-team').resolve()))
from install_paths import bootstrap_runtime, import_adapters_cursor

root = Path('.').resolve()
bootstrap_runtime(root)
agent_cli = import_adapters_cursor('runtime.agent_cli')
assert hasattr(agent_cli, 'is_real_agent_launch_enabled')
from governed_ai.adapters.cursor.adapter import CursorAdapter
adapter = CursorAdapter(project_root=root)
descriptor = adapter.describe()
assert descriptor['adapter_id'] == 'cursor'
assert 'linux' in descriptor['platforms']
print('OK')
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_fresh_install_imports_claude_code_adapter_without_top_level_adapters(
    tmp_path: Path,
) -> None:
    """Mirrors test_fresh_install_imports_cursor_adapter_without_top_level_adapters
    for the second Adaptateur — the same installed-layout aliasing
    (_ensure_adapter_alias) must work for adapters.claude_code too."""
    target = tmp_path / "installed"
    install = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "portability-smoke-claude-code",
            "--project-name",
            "Portability Smoke Claude Code",
            "--adapter",
            "claude-code",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    assert not (target / "adapters").exists()
    assert (target / "scripts" / "ai-team" / "install_paths.py").is_file()

    result = _run_python(
        target,
        """
from pathlib import Path
import sys
sys.path.insert(0, str(Path('scripts/ai-team').resolve()))
from install_paths import bootstrap_runtime, import_adapter_module

root = Path('.').resolve()
bootstrap_runtime(root)
checks = import_adapter_module('claude_code', 'runtime.checks')
assert hasattr(checks, 'platform_profile')
from governed_ai.adapters.claude_code.adapter import ClaudeCodeAdapter
adapter = ClaudeCodeAdapter(project_root=root)
descriptor = adapter.describe()
assert descriptor['adapter_id'] == 'claude-code'
assert 'linux' in descriptor['platforms']
print('OK')
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_orchestrate_source_avoids_bare_adapter_imports() -> None:
    """orchestrate.py must import CursorAdapter/ClaudeCodeAdapter through the
    layout-safe governed_ai.adapters.* namespace, never a bare adapters.*
    import that would break in installed layout without the alias."""
    text = (REPO_ROOT / "scripts" / "ai-team" / "orchestrate.py").read_text(encoding="utf-8")
    assert "from adapters.cursor.runtime.agent_cli import" not in text
    assert "from adapters.cursor." not in text
    assert "from adapters.claude_code." not in text
    assert "from governed_ai.adapters.cursor.adapter import CursorAdapter" in text
    assert "from governed_ai.adapters.claude_code.adapter import ClaudeCodeAdapter" in text
