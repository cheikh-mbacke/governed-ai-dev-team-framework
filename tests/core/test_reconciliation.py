"""Pre-compile reconciliation baseline tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from governed_ai.core.reconciliation import (
    REPORT_RELATIVE_PATH,
    fingerprint_project,
    new_report,
    semantic_issues,
)


def _ready_report(root: Path) -> dict:
    docs = root / "docs" / "product"
    docs.mkdir(parents=True, exist_ok=True)
    sources = []
    for key in (
        "objectives",
        "users",
        "business_rules",
        "constraints",
        "out_of_scope",
        "prior_decisions",
        "acceptance_criteria",
    ):
        path = docs / f"{key}.md"
        path.write_text(f"# {key}\n", encoding="utf-8")
        sources.append(
            {
                "id": f"SRC-{key}",
                "type": (
                    "recorded_human_decision"
                    if key == "prior_decisions"
                    else "human_construction_material"
                ),
                "path": path.relative_to(root).as_posix(),
                "authority": "human",
                "scope": "reconciliation-test",
                "version": "1",
                "status": "active",
            }
        )
    registry = root / ".ai-team" / "sources" / "source-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        yaml.safe_dump({"registry_version": "1.0", "sources": sources}, sort_keys=False),
        encoding="utf-8",
    )
    report = new_report("test-project", root, "2026-09-04T00:00:00+00:00")
    for key, entry in report["human_material"].items():
        entry.update(
            {
                "status": "sufficient",
                "source_refs": [f"SRC-{key}"],
                "note": "Reviewed with the human authority.",
            }
        )
    report["status"] = "approved"
    report["convergence"] = [
        {
            "id": f"REC-{index:03d}",
            "subject": entry["path"],
            "classification": "conformant",
            "intent_refs": ["SRC-objectives"],
            "evidence": "Observed implementation matches the described behavior.",
            "action": "keep",
            "resolution_status": "completed",
            "verification": "Focused tests pass.",
        }
        for index, entry in enumerate(report["inventory"]["entries"], start=1)
    ]
    report["verification"] = {
        "commands": [
            {"command": "pytest", "status": "pass", "evidence": "1 passed"}
        ],
        "blocking_conflicts": 0,
    }
    return report


def test_fingerprint_excludes_framework_managed_and_reconciliation_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('project')\n", encoding="utf-8")
    managed = tmp_path / "scripts" / "ai-team"
    managed.mkdir(parents=True)
    (managed / "validate.py").write_text("managed-v1\n", encoding="utf-8")
    record_path = tmp_path / ".ai-team" / "installation-record.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "project_id": "test-project",
                "core": {
                    "managed_files": [
                        {"path": "scripts/ai-team/validate.py", "installed_sha256": "sha256:x"}
                    ]
                },
                "distribution": {"managed_files": []},
                "adapters": [],
            }
        ),
        encoding="utf-8",
    )

    before = fingerprint_project(tmp_path)
    (managed / "validate.py").write_text("managed-v2\n", encoding="utf-8")
    report_path = tmp_path / REPORT_RELATIVE_PATH
    report_path.parent.mkdir(parents=True)
    report_path.write_text("status: draft\n", encoding="utf-8")
    after_managed_change = fingerprint_project(tmp_path)
    assert before == after_managed_change

    (tmp_path / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    assert fingerprint_project(tmp_path).digest != before.digest


def test_ready_reconciliation_accepts_matching_fingerprint(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    report = _ready_report(tmp_path)
    report["status"] = "ready"
    report["baseline"] = {
        **fingerprint_project(tmp_path).as_dict(),
        "verified_at": "2026-09-04T00:00:00+00:00",
    }
    assert semantic_issues(
        report,
        root=tmp_path,
        require_ready=True,
        verify_fingerprint=True,
    ) == []


def test_project_change_invalidates_ready_reconciliation(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    app = tmp_path / "src" / "app.py"
    app.write_text("print('ok')\n", encoding="utf-8")
    report = _ready_report(tmp_path)
    report["status"] = "ready"
    report["baseline"] = {
        **fingerprint_project(tmp_path).as_dict(),
        "verified_at": "2026-09-04T00:00:00+00:00",
    }

    app.write_text("print('stale')\n", encoding="utf-8")
    issues = semantic_issues(
        report,
        root=tmp_path,
        require_ready=True,
        verify_fingerprint=True,
    )
    assert any("baseline is stale" in issue for issue in issues)


def test_destructive_action_requires_human_approval_reference(tmp_path: Path) -> None:
    report = _ready_report(tmp_path)
    report["convergence"][0].update(
        {
            "classification": "obsolete_out_of_scope",
            "action": "delete",
        }
    )
    issues = semantic_issues(report, root=tmp_path)
    assert any("requires human_approval_ref" in issue for issue in issues)

    report["convergence"][0]["human_approval_ref"] = "DEC-REC-001"
    assert semantic_issues(report, root=tmp_path) == []


def test_missing_human_material_and_open_decision_block(tmp_path: Path) -> None:
    report = _ready_report(tmp_path)
    report["human_material"]["business_rules"] = {
        "status": "ambiguous",
        "source_refs": [],
        "note": "Conflicting descriptions.",
    }
    report["decisions"] = [
        {"id": "DEC-REC-002", "question": "Which rule applies?", "status": "open"}
    ]
    issues = semantic_issues(report, root=tmp_path)
    assert any("business_rules" in issue for issue in issues)
    assert any("DEC-REC-002" in issue for issue in issues)


def test_not_applicable_material_still_requires_human_trace(tmp_path: Path) -> None:
    report = _ready_report(tmp_path)
    report["human_material"]["prior_decisions"] = {
        "status": "not_applicable",
        "source_refs": [],
        "note": "",
    }
    issues = semantic_issues(report, root=tmp_path)
    assert any("authoritative source_ref" in issue for issue in issues)
    assert any("not_applicable needs an explanation" in issue for issue in issues)


def test_inventory_surface_requires_convergence_classification(tmp_path: Path) -> None:
    report = _ready_report(tmp_path)
    report["inventory"]["entries"].append(
        {"path": "legacy", "kind": "code", "evidence": "Observed application code."}
    )
    issues = semantic_issues(report, root=tmp_path)
    assert any("inventory surface 'legacy'" in issue for issue in issues)


def test_unknown_intent_source_and_untraced_resolution_block(tmp_path: Path) -> None:
    report = _ready_report(tmp_path)
    report["convergence"][0]["intent_refs"] = ["SRC-UNKNOWN"]
    report["decisions"] = [
        {"id": "DEC-REC-003", "question": "Resolved how?", "status": "resolved"}
    ]
    issues = semantic_issues(report, root=tmp_path)
    assert any("SRC-UNKNOWN" in issue for issue in issues)
    assert any("needs resolution_ref" in issue for issue in issues)


def test_report_schema_accepts_a_complete_ready_document(tmp_path: Path) -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "distribution"
        / "payload"
        / ".ai-team"
        / "schemas"
        / "reconciliation.schema.json"
    )
    report = _ready_report(tmp_path)
    report["status"] = "ready"
    report["baseline"] = {
        **fingerprint_project(tmp_path).as_dict(),
        "verified_at": "2026-09-04T00:00:00+00:00",
    }
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(report)) == []
    assert yaml.safe_load(yaml.safe_dump(report)) == report
