"""Phase 7: member cwd (INS-AC-016) and active-ensemble workspace (INS-AC-017)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import yaml
from adapters.cursor.compiler.ensemble_workspace import (
    render_code_workspace,
    write_active_ensemble_workspace,
)

from governed_ai.adapters.claude_code.adapter import ClaudeCodeAdapter
from governed_ai.adapters.cursor.adapter import CursorAdapter
from governed_ai.core.ensemble_workspace import (
    active_ensemble_folders,
    apply_member_execution_fields,
    execution_project_root,
    product_work_unit_missing_member_id,
)
from governed_ai.core.workspace import Workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_V1 = REPO_ROOT / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
BASE_SHA = "a" * 40


def _write_multi_member_instance(tmp_path: Path) -> tuple[Workspace, Path, Path, Path]:
    instance = tmp_path / "acme-ai-team"
    backend = tmp_path / "boutique-api"
    frontend = tmp_path / "boutique-web"
    intranet_api = tmp_path / "intranet-api"
    instance.mkdir()
    backend.mkdir()
    frontend.mkdir()
    intranet_api.mkdir()
    ai_team = instance / ".ai-team"
    ai_team.mkdir()
    (ai_team / "project-profile.yaml").write_text(
        "project:\n  id: acme-ai-team\n", encoding="utf-8"
    )
    (ai_team / "active-ensemble.yaml").write_text(
        "ensemble_id: boutique\n", encoding="utf-8"
    )
    boutique = ai_team / "ensembles" / "boutique"
    boutique.mkdir(parents=True)
    (boutique / "members.yaml").write_text(
        yaml.safe_dump(
            {
                "ensemble_id": "boutique",
                "members": [
                    {"id": "backend", "kind": "service", "path": "../boutique-api"},
                    {"id": "frontend", "kind": "ui", "path": "../boutique-web"},
                ],
            }
        ),
        encoding="utf-8",
    )
    intranet = ai_team / "ensembles" / "intranet"
    intranet.mkdir(parents=True)
    (intranet / "members.yaml").write_text(
        yaml.safe_dump(
            {
                "ensemble_id": "intranet",
                "members": [
                    {"id": "api", "kind": "service", "path": "../intranet-api"},
                ],
            }
        ),
        encoding="utf-8",
    )
    workspace = Workspace.from_root(instance)
    return workspace, backend, frontend, intranet_api


def _spi_request(execution_id: str, *, execution_workspace: Path) -> dict:
    return {
        "protocol_version": "1.0",
        "execution_id": execution_id,
        "correlation_id": "COR-INS-AC-016",
        "adapter": {"id": "cursor", "version": "0.1.0"},
        "contract": {
            "bundle_version": "1.0.0",
            "bundle_hash": "sha256:" + "b" * 64,
            "role_id": "backend-developer",
            "role_revision": "1.0.0",
            "procedure_id": "implement-work-unit",
            "procedure_revision": "1.0.0",
        },
        "project_id": "runtime-test",
        "work_unit_id": "WU-INS-AC-016",
        "base_sha": BASE_SHA,
        "context_package_ref": "CTX-INS",
        "resolved_scope": ["src/"],
        "approvals": [],
        "requested_at": "2026-09-18T18:00:00+00:00",
        "execution_workspace": str(execution_workspace),
        "member_id": "frontend",
        "member_root": str(execution_workspace),
    }


def test_ins_ac_016_execution_workspace_is_member_never_instance(
    tmp_path: Path,
) -> None:
    workspace, backend, frontend, _intranet = _write_multi_member_instance(tmp_path)
    request: dict = {
        "execution_workspace": str(frontend),
        "member_id": "frontend",
        "member_root": str(frontend),
    }
    resolved = execution_project_root(workspace.instance_root, request)
    assert resolved == frontend.resolve()
    assert resolved != workspace.instance_root.resolve()
    assert resolved != backend.resolve()


def test_ins_ac_016_apply_member_fields_and_integration_omits_member_id(
    tmp_path: Path,
) -> None:
    workspace, backend, _frontend, _intranet = _write_multi_member_instance(tmp_path)
    product = {"id": "WU-FE", "kind": "feature", "member_id": "backend"}
    request: dict = {"execution_workspace": str(backend)}
    apply_member_execution_fields(workspace, product, request)
    assert request["member_id"] == "backend"
    assert Path(request["member_root"]) == backend.resolve()

    integration = {"id": "WU-INT", "kind": "integration"}
    assert product_work_unit_missing_member_id(workspace, integration) is False
    assert product_work_unit_missing_member_id(workspace, {"id": "WU-X"}) is True
    integration_request: dict = {"execution_workspace": str(workspace.instance_root)}
    apply_member_execution_fields(workspace, integration, integration_request)
    assert "member_id" not in integration_request
    assert Path(integration_request["execution_workspace"]) == workspace.instance_root.resolve()


def test_ins_ac_016_cursor_and_claude_execute_use_member_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    member = tmp_path / "boutique-web"
    instance = tmp_path / "acme-ai-team"
    member.mkdir()
    instance.mkdir()
    (instance / ".ai-team").mkdir()
    captured: list[Path] = []

    def _capture(project_root: Path, request: dict) -> dict:
        captured.append(Path(project_root).resolve())
        return {
            "protocol_version": "1.0",
            "execution_id": request["execution_id"],
            "adapter": {"id": "stub", "version": "0.0.0"},
            "contract": request["contract"],
            "status": "blocked",
            "summary": "stub",
            "started_at": "2026-09-18T18:00:00+00:00",
            "finished_at": "2026-09-18T18:00:01+00:00",
            "artifacts": [],
            "checks": [],
            "limitations": ["stub"],
        }

    monkeypatch.setattr(
        "governed_ai.adapters.cursor.adapter.execute_runtime", _capture
    )
    monkeypatch.setattr(
        "governed_ai.adapters.claude_code.adapter.execute_runtime", _capture
    )
    request = _spi_request("EXE-INS-016", execution_workspace=member)

    cursor = CursorAdapter(project_root=instance, bundle_dir=BUNDLE_V1)
    claude = ClaudeCodeAdapter(project_root=instance, bundle_dir=BUNDLE_V1)
    cursor.execute(request)  # type: ignore[arg-type]
    claude.execute({**request, "adapter": {"id": "claude-code", "version": "0.1.0"}})  # type: ignore[arg-type]

    assert captured == [member.resolve(), member.resolve()]
    assert "execution_project_root" in inspect.getsource(CursorAdapter.execute)
    assert "execution_project_root" in inspect.getsource(ClaudeCodeAdapter.execute)


def test_ins_ac_017_workspace_lists_instance_and_active_members_only(
    tmp_path: Path,
) -> None:
    workspace, backend, frontend, intranet_api = _write_multi_member_instance(tmp_path)
    folders = active_ensemble_folders(workspace)
    names = [item["name"] for item in folders]
    paths = {item["name"]: Path(item["path"]).resolve() for item in folders}
    assert names == ["instance", "backend", "frontend"]
    assert paths["instance"] == workspace.instance_root.resolve()
    assert paths["backend"] == backend.resolve()
    assert paths["frontend"] == frontend.resolve()
    assert intranet_api.resolve() not in paths.values()

    written = write_active_ensemble_workspace(workspace)
    assert written is not None
    assert written == workspace.instance_root / "boutique.code-workspace"
    document = json.loads(written.read_text(encoding="utf-8"))
    assert document == render_code_workspace(folders, name="boutique")
    listed = {entry["name"]: Path(entry["path"]).resolve() for entry in document["folders"]}
    assert set(listed) == {"instance", "backend", "frontend"}
    assert intranet_api.resolve() not in listed.values()
