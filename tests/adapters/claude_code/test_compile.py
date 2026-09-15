"""Claude Code compiler — pilot-role frontmatter rendering (AD-002/AD-003)."""

from __future__ import annotations

from pathlib import Path

from adapters.claude_code.compiler.compile import compile_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"


def test_compile_produces_expected_pilot_artifacts(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    manifest = compile_manifest(BUNDLE_V1, staging)
    paths = {entry["path"] for entry in manifest["artifacts"]}
    assert paths == {
        ".claude/CLAUDE.md",
        ".claude/agents/auditor.md",
        ".claude/agents/backend-developer.md",
        ".claude/settings.json",
    }
    assert manifest["adapter_id"] == "claude-code"
    assert manifest["bundle_version"] == "1.0.0"


def test_readonly_role_gets_restrictive_tools_list(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    compile_manifest(BUNDLE_V1, staging)
    auditor = (staging / ".claude/agents/auditor.md").read_text(encoding="utf-8")
    assert "name: auditor" in auditor
    assert "tools: Read, Grep, Glob" in auditor
    assert "Write" not in auditor.split("---")[1]
    assert "Edit" not in auditor.split("---")[1]


def test_scoped_write_role_gets_no_tools_restriction(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    compile_manifest(BUNDLE_V1, staging)
    backend = (staging / ".claude/agents/backend-developer.md").read_text(encoding="utf-8")
    assert "name: backend-developer" in backend
    frontmatter = backend.split("---")[1]
    assert "tools:" not in frontmatter


def test_compile_is_deterministic(tmp_path: Path) -> None:
    manifest_a = compile_manifest(BUNDLE_V1, tmp_path / "a")
    manifest_b = compile_manifest(BUNDLE_V1, tmp_path / "b")
    assert manifest_a == manifest_b
    for entry in manifest_a["artifacts"]:
        rel = entry["path"]
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes()
