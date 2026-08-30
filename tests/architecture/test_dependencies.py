"""Document 11 §5 rule 1 / Document 14 §12: Core must not import Cursor or Distribution."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = ROOT / "src" / "governed_ai" / "core"
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

FORBIDDEN_MODULE_PREFIXES = (
    "adapters.cursor",
    "governed_ai.adapters.cursor",
    "distribution",
    "governed_ai.distribution",
)


def _is_forbidden_module(name: str | None) -> bool:
    if not name:
        return False
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        if name == prefix or name.startswith(prefix + "."):
            return True
    return False


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def find_forbidden_imports(root: Path) -> list[str]:
    """Return human-readable violations for forbidden Import / ImportFrom nodes."""
    violations: list[str] = []
    for path in _iter_python_files(root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        rel = path.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_module(alias.name):
                        violations.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _is_forbidden_module(module):
                    violations.append(f"{rel}:{node.lineno}: from {module} import ...")
                    continue
                if module:
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        combined = f"{module}.{alias.name}"
                        if _is_forbidden_module(combined):
                            violations.append(
                                f"{rel}:{node.lineno}: from {module} import {alias.name}"
                            )
    return violations


def test_core_does_not_import_adapters_cursor_or_distribution() -> None:
    violations = find_forbidden_imports(CORE_ROOT)
    assert violations == [], (
        "Core must not import adapters.cursor or distribution:\n" + "\n".join(violations)
    )


def test_forbidden_import_detector_flags_negative_fixture() -> None:
    """Proof the guard would fail if a Cursor/Distribution import appeared."""
    violations = find_forbidden_imports(FIXTURES_ROOT)
    assert any("adapters.cursor" in v for v in violations)
    assert any("distribution" in v for v in violations)
