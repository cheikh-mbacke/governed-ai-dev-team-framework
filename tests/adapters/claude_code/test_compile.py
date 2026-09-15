"""Claude Code compiler — role/skill frontmatter rendering (AD-002/AD-003)."""

from __future__ import annotations

from pathlib import Path

from adapters.claude_code.compiler.compile import BUNDLE_ROLE_AGENT, compile_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
TEMPLATES_CLAUDE = REPO_ROOT / "adapters" / "claude_code" / "templates" / ".claude"


def test_compile_produces_one_artifact_per_template_file(tmp_path: Path) -> None:
    """The compiled artifact set must exactly mirror the template tree —
    computed from disk rather than hardcoded, since it grows with every
    role/skill added and would otherwise silently drift."""
    staging = tmp_path / "staging"
    manifest = compile_manifest(BUNDLE_V1, staging)
    paths = {entry["path"] for entry in manifest["artifacts"]}
    expected = {
        f".claude/{p.relative_to(TEMPLATES_CLAUDE).as_posix()}"
        for p in TEMPLATES_CLAUDE.rglob("*")
        if p.is_file()
    }
    assert paths == expected
    assert manifest["adapter_id"] == "claude-code"
    assert manifest["bundle_version"] == "1.0.0"


def test_every_bundle_role_agent_has_a_template(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    manifest = compile_manifest(BUNDLE_V1, staging)
    paths = {entry["path"] for entry in manifest["artifacts"]}
    for role_id in BUNDLE_ROLE_AGENT:
        assert f".claude/agents/{role_id}.md" in paths


def test_no_compiled_agent_leaks_cursor_only_readonly_key(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    compile_manifest(BUNDLE_V1, staging)
    for agent_path in sorted((staging / ".claude" / "agents").glob("*.md")):
        frontmatter = agent_path.read_text(encoding="utf-8").split("---")[1]
        assert "readonly" not in frontmatter, agent_path


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


def test_every_readonly_bundle_role_gets_restrictive_tools_list(tmp_path: Path) -> None:
    import json

    staging = tmp_path / "staging"
    compile_manifest(BUNDLE_V1, staging)
    for role_id in BUNDLE_ROLE_AGENT:
        role = json.loads((BUNDLE_V1 / "roles" / f"{role_id}.json").read_text(encoding="utf-8"))
        rendered = (staging / f".claude/agents/{role_id}.md").read_text(encoding="utf-8")
        frontmatter = rendered.split("---")[1]
        if role["writes"]["product"]["level"] == "none":
            assert "tools: Read, Grep, Glob" in frontmatter, role_id
        else:
            assert "tools:" not in frontmatter, role_id


def test_compiled_skills_have_no_leftover_cursor_path_references(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    compile_manifest(BUNDLE_V1, staging)
    for skill_file in sorted((staging / ".claude" / "skills").rglob("*")):
        if skill_file.is_file():
            assert ".cursor" not in skill_file.read_text(encoding="utf-8", errors="ignore"), (
                skill_file
            )


def test_compile_includes_all_hook_scripts(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    manifest = compile_manifest(BUNDLE_V1, staging)
    paths = {entry["path"] for entry in manifest["artifacts"]}
    for script in ("audit_event.py", "guard_shell.py", "session_init.py", "backup_push.py", "run_hook.cmd"):
        assert f".claude/hooks/{script}" in paths


def test_compile_is_deterministic(tmp_path: Path) -> None:
    manifest_a = compile_manifest(BUNDLE_V1, tmp_path / "a")
    manifest_b = compile_manifest(BUNDLE_V1, tmp_path / "b")
    assert manifest_a == manifest_b
    for entry in manifest_a["artifacts"]:
        rel = entry["path"]
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes()
