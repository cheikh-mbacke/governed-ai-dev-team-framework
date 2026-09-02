"""Document 11 §5 rule 5 / Document 14 §12: no named IDE artefacts in Core or contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = ROOT / "src" / "governed_ai" / "core"
CONTRACTS_ROOT = ROOT / "src" / "governed_ai" / "contracts"
CONSTITUTION_ROOT = ROOT / "distribution" / "payload" / ".ai-team" / "constitution"
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

# AC tokens plus Document 14 parity (Claude Code, Codex).
FORBIDDEN_TOKENS = (
    ".cursor",
    "Cursor",
    "hooks.json",
    "permissions.json",
    "cli.json",
    "Claude Code",
    "Codex",
)

_SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".toml", ".txt", ".ini"}


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def find_named_tool_leaks(root: Path) -> list[str]:
    """Return violations for forbidden tool/IDE token strings under root."""
    violations: list[str] = []
    for path in _iter_source_files(root):
        text = path.read_text(encoding="utf-8")
        rel = path.as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in FORBIDDEN_TOKENS:
                if token in line:
                    violations.append(f"{rel}:{lineno}: contains {token!r}")
    return violations


def test_core_has_no_named_tool_leaks() -> None:
    violations = find_named_tool_leaks(CORE_ROOT)
    assert violations == [], "Forbidden named-tool tokens in core:\n" + "\n".join(violations)


def test_contracts_have_no_named_tool_leaks() -> None:
    violations = find_named_tool_leaks(CONTRACTS_ROOT)
    assert violations == [], (
        "Forbidden named-tool tokens in contracts:\n" + "\n".join(violations)
    )


def test_constitution_has_no_named_tool_leaks() -> None:
    violations = find_named_tool_leaks(CONSTITUTION_ROOT)
    assert violations == [], (
        "Forbidden named-tool tokens in constitution:\n" + "\n".join(violations)
    )


def test_named_tool_leak_detector_flags_negative_fixture() -> None:
    """Proof the guard would fail if Cursor/.cursor artefacts appeared."""
    violations = find_named_tool_leaks(FIXTURES_ROOT)
    for token in FORBIDDEN_TOKENS:
        assert any(token in v for v in violations), f"detector missed {token!r}"
