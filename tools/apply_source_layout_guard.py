#!/usr/bin/env python3
"""Apply WU-SOURCE-LAYOUT-GUARD in one atomic run."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VIRGIN_STATE = """project_id: framework-renov
constitution_version: 1.2.0
phase: not_compiled
gates:
  G0:
    status: not_required
  G1:
    status: not_required
  G2:
    status: not_required
  G3:
    status: not_required
  G4:
    status: not_required
work_units: {}
dependency_edges: []
active_workers: []
open_decisions: []
open_blockers: []
open_defects: []
open_findings: []
last_updated: '2026-09-01T00:00:00+00:00'
"""

WORKSPACE_MODE = Path(__file__).with_name("_workspace_mode_body.py")
# inline below after import failure guard

WORKSPACE_MODE_SRC = r'''"""Distinguish framework source repositories from installed client workspaces."""

from __future__ import annotations

from pathlib import Path

from governed_ai.core.workspace import Workspace

FRAMEWORK_SOURCE_KIND = "framework_source"
FEEDBACK_REFERENCE_FIXTURE = "tests/fixtures/projects/clean/"

FEEDBACK_FORBIDDEN_MESSAGE = (
    "Feedback commands are not allowed on a framework_source repository. "
    "This directory builds the framework; use an installed target project or "
    f"{FEEDBACK_REFERENCE_FIXTURE} to exercise the feedback loop."
)

CLIENT_CYCLE_DIRECTORIES = (
    "work-units",
    "events",
    "evidence",
    "decisions",
    "context-packages",
    "acceptance",
    "authorizations",
    "releases",
)


def read_repository_kind(root: Path) -> str | None:
    profile = root / ".ai-team" / "project-profile.yaml"
    if not profile.is_file():
        return None
    for line in profile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


def is_framework_source(workspace: Workspace | Path) -> bool:
    root = workspace.root if isinstance(workspace, Workspace) else Path(workspace).resolve()
    return read_repository_kind(root) == FRAMEWORK_SOURCE_KIND


def ensure_feedback_allowed(workspace: Workspace) -> None:
    if is_framework_source(workspace):
        from governed_ai.core.commands.errors import ErrorCode, GatewayError

        raise GatewayError(
            ErrorCode.UNSUPPORTED_CONTRACT,
            FEEDBACK_FORBIDDEN_MESSAGE,
            "/workspace",
        )


def collect_framework_source_feedback_artifacts(ai_team: Path) -> list[str]:
    errors: list[str] = []
    for pattern, label in (
        ("observations/OBS-*.yaml", "observation"),
        ("retrospectives/RET-*.yaml", "retrospective"),
        ("metrics/framework-feedback-*.json", "feedback export"),
    ):
        for path in sorted(ai_team.glob(pattern)):
            errors.append(
                f"framework_source repository must not contain client feedback {label} "
                f"({path.relative_to(ai_team.parent).as_posix()})"
            )
    return errors


def collect_framework_source_client_cycle_artifacts(
    ai_team: Path, *, state: dict | None = None
) -> list[str]:
    errors: list[str] = []
    if state is not None:
        if state.get("phase") != "not_compiled":
            errors.append(
                "framework_source repository project-state.yaml phase must be "
                f"'not_compiled' (found {state.get('phase')!r})"
            )
        if state.get("work_units"):
            errors.append(
                "framework_source repository project-state.yaml work_units must be empty"
            )
        for field in ("milestones", "increments", "releases", "critical_path"):
            if state.get(field):
                errors.append(
                    f"framework_source repository project-state.yaml must not define {field}"
                )

    for directory in CLIENT_CYCLE_DIRECTORIES:
        for path in sorted((ai_team / directory).glob("*.yaml")):
            errors.append(
                "framework_source repository must not contain client-cycle artifacts "
                f"({path.relative_to(ai_team.parent).as_posix()})"
            )
        for path in sorted((ai_team / directory).glob("*.json")):
            if path.name == ".gitkeep":
                continue
            errors.append(
                "framework_source repository must not contain client-cycle artifacts "
                f"({path.relative_to(ai_team.parent).as_posix()})"
            )
    return errors
'''

RULE_MDC = """---
description: >-
  When repository_kind is framework_source, this repo builds the framework; it
  does not run the client governance cycle (compile-project, gates, Work Units).
alwaysApply: true
---
# Framework source workspace layout

Read `.ai-team/project-profile.yaml` → `project.repository_kind` first.

When `repository_kind` is `framework_source`:

- This repository **builds** the framework. It is **not** an installed client
  project and must not be analyzed as one.
- `.ai-team/state/project-state.yaml` is a **virgin template** (`phase:
  not_compiled`, empty `work_units`). Do not treat it as an active client
  runtime or execution plan.
- Do **not** run `/compile-project`, gate commands, or client Work Unit cycles
  here. Framework development on this repo does not use the installed-client
  orchestration path.
- Edit implementation code under `src/governed_ai/`, `adapters/`, and
  `distribution/`. Never create `.ai-team/runtime/` or
  `installation-record.json` here.
- To observe installed behavior, use `tests/fixtures/projects/clean/` or
  `python tools/install.py --target <dir>` in a separate directory.
- Do not run `scripts/ai-team/feedback.py` record, retrospective, or export here.

When `repository_kind` is not `framework_source`, ignore the rules above.
"""

SESSION_INIT = """#!/usr/bin/env python3
import json
import os
from pathlib import Path

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
profile = root / ".ai-team" / "project-profile.yaml"


def _repository_kind(profile_path: Path) -> str | None:
    if not profile_path.is_file():
        return None
    for line in profile_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


message = (
    "Governed AI Team framework detected. Read .ai-team/project-profile.yaml before "
    "inferring how this repository is organized."
)
if _repository_kind(profile) == "framework_source":
    message += (
        " Workspace mode: framework_source (fabrication). This repo builds the framework;"
        " it is not an installed client project and does not run compile-project or"
        " client Work Unit cycles here. project-state.yaml is a virgin template only."
        " Edit src/ and adapters/. Installed-layout reference:"
        " tests/fixtures/projects/clean/. Never run tools/install.py --target . here."
    )
else:
    message += (
        " Read .ai-team/state/project-state.yaml before runtime activation when no"
        " approved execution plan exists. Use /compile-project when required."
    )
print(json.dumps({"additional_context": message}))
"""

AGENTS_MD = """# Governed AI Team Instructions

This repository uses the Engineering Constitution under `.ai-team/constitution/`.

## Framework source repository

If `.ai-team/project-profile.yaml` declares `repository_kind: framework_source`,
this repo **builds** the framework — it is **not** an installed client project.

- Edit framework code under `src/`, `adapters/`, `distribution/`, and the
  installable payload under `.ai-team/constitution/`, `.ai-team/schemas/`,
  `.ai-team/contracts/`, `.ai-team/templates/`.
- `.ai-team/state/project-state.yaml` is a **virgin template** (`phase:
  not_compiled`, empty `work_units`). It is not an active client runtime.
- Do **not** run `/compile-project`, client gate cycles, or Work Unit orchestration
  on this repository.
- Do **not** create `.ai-team/runtime/` or `.ai-team/installation-record.json` here.
- Do **not** run `scripts/ai-team/feedback.py` record, retrospective, or export here.
- Do **not** edit `tests/fixtures/projects/clean|legacy/` to change product behavior.
- To test installed behavior, use `tests/fixtures/projects/clean/` or
  `python tools/install.py --target <separate-dir>` — never `--target .` on this repo.
- After changing the installable payload:
  `python scripts/ai-team/sync_source_manifest.py` then `python scripts/ai-team/validate.py`

Before making framework code changes:

1. Read `.ai-team/project-profile.yaml` to confirm `repository_kind:
   framework_source`.
2. Do not invent missing product or policy decisions; update human product sources
   under `docs/product/` when intent changes.
3. Treat repository/runtime observations as evidence, not as permission to
   contradict human authoritative sources.
4. When execution exposes reusable friction on an **installed target project**,
   record it there with `python scripts/ai-team/feedback.py record` — not in this
   source repository.
5. Follow `VERSIONING.md` for branch names, commit messages, merge strategy,
   version changes, tags, releases, maintenance branches, and history cutovers.
"""

WORKSPACE_HELPERS = '''"""Shared helpers for core tests that simulate installed client workspaces."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_installed_client_profile(
    ai_team: Path,
    *,
    project_id: str = "test-project",
) -> None:
    source_profile = REPO_ROOT / ".ai-team" / "project-profile.yaml"
    profile = yaml.safe_load(source_profile.read_text(encoding="utf-8")) or {}
    project = profile.setdefault("project", {})
    project["id"] = project_id
    project["repository_kind"] = "existing_or_greenfield_project"
    (ai_team / "project-profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
'''

TEST_WORKSPACE_MODE = '''"""Tests for framework_source workspace guards."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import (
    collect_framework_source_client_cycle_artifacts,
    is_framework_source,
    read_repository_kind,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_read_repository_kind_on_source_repo() -> None:
    assert read_repository_kind(REPO_ROOT) == "framework_source"


def test_is_framework_source_on_source_repo() -> None:
    assert is_framework_source(Workspace.from_root(REPO_ROOT))


def test_project_state_is_virgin() -> None:
    import yaml

    state = yaml.safe_load(
        (REPO_ROOT / ".ai-team" / "state" / "project-state.yaml").read_text(encoding="utf-8")
    )
    assert state["phase"] == "not_compiled"
    assert state["work_units"] == {}


def test_no_client_cycle_artifacts_on_source_repo() -> None:
    import yaml

    state = yaml.safe_load(
        (REPO_ROOT / ".ai-team" / "state" / "project-state.yaml").read_text(encoding="utf-8")
    )
    assert collect_framework_source_client_cycle_artifacts(REPO_ROOT / ".ai-team", state=state) == []


def test_feedback_record_blocked_on_framework_source() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ai-team/feedback.py",
            "record",
            "--category",
            "tooling",
            "--symptom",
            "should be blocked on framework_source",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "framework_source" in (result.stderr + result.stdout).lower()


def test_validate_passes_on_source_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ai-team/validate.py"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr + result.stdout
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def git_rm_artifacts() -> None:
    globs = [
        ".ai-team/work-units/*.yaml",
        ".ai-team/events/*.yaml",
        ".ai-team/decisions/*.yaml",
        ".ai-team/context-packages/*.yaml",
        ".ai-team/retrospectives/RET-*.yaml",
    ]
    paths: list[str] = []
    for pattern in globs:
        paths.extend(str(p) for p in ROOT.glob(pattern))
    if paths:
        subprocess.run(["git", "rm", "-f", *paths], cwd=ROOT, check=False)
    for rel in (".ai-team/evidence", ".ai-team/acceptance", ".ai-team/authorizations"):
        if (ROOT / rel).exists():
            subprocess.run(["git", "rm", "-rf", rel], cwd=ROOT, check=False)
    for rel in (".ai-team/evidence", ".ai-team/acceptance"):
        write(ROOT / rel / ".gitkeep", "")


def patch_validate() -> None:
    path = ROOT / "scripts/ai-team/validate.py"
    text = path.read_text(encoding="utf-8")
    if "workspace_mode" not in text:
        text = text.replace(
            "from i18n import project_language, t\n\nROOT = _ROOT",
            "from i18n import project_language, t\n\n"
            "from install_paths import bootstrap_runtime\n\n"
            "bootstrap_runtime(_ROOT)\n\n"
            "from governed_ai.core.workspace_mode import (\n"
            "    collect_framework_source_client_cycle_artifacts,\n"
            "    collect_framework_source_feedback_artifacts,\n"
            ")\n\n"
            "ROOT = _ROOT",
        )
        text = text.replace(
            '        if (AI / "runtime" / "governed_ai").is_dir():\n'
            "            errors.append(\n"
            '                "framework_source repository must not contain "\n'
            '                ".ai-team/runtime/governed_ai/ (installed-target layout only)"\n'
            "            )\n"
            "        if isinstance(version_manifest, dict):",
            '        if (AI / "runtime" / "governed_ai").is_dir():\n'
            "            errors.append(\n"
            '                "framework_source repository must not contain "\n'
            '                ".ai-team/runtime/governed_ai/ (installed-target layout only)"\n'
            "            )\n"
            '        source_state_path = AI / "state" / "project-state.yaml"\n'
            "        state_for_checks = load_yaml(source_state_path) if source_state_path.exists() else {}\n"
            "        errors.extend(collect_framework_source_feedback_artifacts(AI))\n"
            "        errors.extend(\n"
            "            collect_framework_source_client_cycle_artifacts(AI, state=state_for_checks)\n"
            "        )\n"
            "        if isinstance(version_manifest, dict):",
        )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_handler(rel: str, anchor: str, insert: str) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    if "ensure_feedback_allowed" in text:
        return
    text = text.replace(
        "from governed_ai.core.persistence.transaction import Transaction\n",
        "from governed_ai.core.persistence.transaction import Transaction\n"
        "from governed_ai.core.workspace_mode import ensure_feedback_allowed\n",
        1,
    )
    text = text.replace(anchor, insert, 1)
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    if ".ai-team/runtime/" not in text:
        block = (
            "# Installed-target layout must not appear on framework_source repositories\n"
            ".ai-team/runtime/\n"
            ".ai-team/installation-record.json\n\n"
            "# Client feedback loop artifacts (belong on installed projects, not the source repo)\n"
            ".ai-team/metrics/framework-feedback-*.json\n"
            ".ai-team/observations/OBS-*.yaml\n"
            ".ai-team/retrospectives/RET-*.yaml\n\n"
        )
        text = text.replace("# AI-team ephemeral/runtime scratch\n", block + "# AI-team ephemeral/runtime scratch\n")
        path.write_text(text, encoding="utf-8", newline="\n")


def patch_profile() -> None:
    path = ROOT / ".ai-team/project-profile.yaml"
    text = path.read_text(encoding="utf-8")
    old = (
        "  note: 'Dépôt source/distribution du framework — pas une cible installée. Seul\n"
        "    framework-version.json décrit le payload ; pas d installation-record.json ici.\n"
        "    Gouvernance de refonte (WU, gates) = métadonnées projet de développement, distinctes\n"
        "    du cycle client post-install. sync_source_manifest.py regénère le manifeste source.'"
    )
    new = (
        "  note: 'Dépôt source du framework — pas une cible installée ni un client en\n"
        "    exécution. project-state.yaml reste vierge (not_compiled). Pas de cycle\n"
        "    compile-project / Work Units ici. framework-version.json décrit le payload ;\n"
        "    pas d installation-record.json. sync_source_manifest.py regénère le manifeste\n"
        "    source.'"
    )
    if old in text:
        text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="\n")


def patch_core_tests() -> None:
    subs = {
        "test_obs_evidence_handlers.py": "framework-renov",
        "test_retro_export_handlers.py": "retro-test",
        "test_legacy_wrappers.py": "wrapper-test",
        "test_gate_acceptance_handlers.py": "gate-test",
    }
    for path in (ROOT / "tests/core").glob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        if 'copy2(source / "project-profile.yaml"' not in text or "write_installed_client_profile" in text:
            continue
        text = text.replace(
            "from governed_ai.core.workspace import Workspace\n\nREPO_ROOT",
            "from governed_ai.core.workspace import Workspace\n\n"
            "from tests.core.workspace_helpers import write_installed_client_profile\n\nREPO_ROOT",
        )
        pid = subs.get(path.name, "test-project")
        repl = (
            "    write_installed_client_profile(ai_team)\n"
            if pid == "test-project"
            else f'    write_installed_client_profile(ai_team, project_id="{pid}")\n'
        )
        text = re.sub(
            r'    shutil\.copy2\(source / "project-profile\.yaml", ai_team / "project-profile\.yaml"\)\n',
            repl,
            text,
            count=1,
        )
        path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    git_rm_artifacts()
    write(ROOT / ".ai-team/state/project-state.yaml", VIRGIN_STATE)
    write(ROOT / "src/governed_ai/core/workspace_mode.py", WORKSPACE_MODE_SRC)
    write(ROOT / ".cursor/rules/05-workspace-layout.mdc", RULE_MDC)
    write(ROOT / "adapters/cursor/templates/.cursor/rules/05-workspace-layout.mdc", RULE_MDC)
    write(ROOT / ".cursor/hooks/session_init.py", SESSION_INIT)
    write(ROOT / "adapters/cursor/templates/.cursor/hooks/session_init.py", SESSION_INIT)
    write(ROOT / "AGENTS.md", AGENTS_MD)
    write(ROOT / "tests/core/workspace_helpers.py", WORKSPACE_HELPERS)
    write(ROOT / "tests/core/test_workspace_mode.py", TEST_WORKSPACE_MODE)
    patch_validate()
    patch_gitignore()
    patch_profile()
    patch_handler(
        "src/governed_ai/core/commands/handlers/record_observation.py",
        '    if not isinstance(payload, dict):\n        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")\n\n    actor = envelope["actor"]',
        '    if not isinstance(payload, dict):\n        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")\n\n    ensure_feedback_allowed(workspace_root)\n\n    actor = envelope["actor"]',
    )
    patch_handler(
        "src/governed_ai/core/commands/handlers/generate_retrospective.py",
        '    if not isinstance(payload, dict):\n        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")\n\n    scope = payload.get("scope")',
        '    if not isinstance(payload, dict):\n        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")\n\n    ensure_feedback_allowed(workspace_root)\n\n    scope = payload.get("scope")',
    )
    patch_handler(
        "src/governed_ai/core/commands/handlers/export_feedback.py",
        '    if not isinstance(payload, dict):\n        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")\n\n    detail_level = payload.get("detail_level", "structured")',
        '    if not isinstance(payload, dict):\n        raise GatewayError(ErrorCode.INVALID_SCHEMA, "payload must be an object", "/payload")\n\n    ensure_feedback_allowed(workspace_root)\n\n    detail_level = payload.get("detail_level", "structured")',
    )
    patch_core_tests()
    subprocess.run([sys.executable, "scripts/ai-team/sync_source_manifest.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/ai-team/validate.py"], cwd=ROOT, check=True)
    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/core/test_workspace_mode.py", "tests/core/", "tests/test_feedback_loop.py", "-q"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "feat(WU-SOURCE-LAYOUT-GUARD): separer depot source et etat client vierge",
        ],
        cwd=ROOT,
        check=True,
    )
    print("SUCCESS")


if __name__ == "__main__":
    main()
