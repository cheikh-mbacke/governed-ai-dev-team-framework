"""Adoption assessment CLI and library tests (Documents 19–20)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from distribution.installer.assessment import (
    ASSESSMENT_SKIP_ENV,
    CATEGORIES,
    DEFAULT_RESOLUTION_OPTIONS,
    REPORT_KIND,
    Finding,
    assessment_gate_error,
    blocking_is_resolved,
    compute_verdict,
    run_assessment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSESS = REPO_ROOT / "tools" / "assess.py"
ASSESS_SKILL = REPO_ROOT / ".cursor" / "skills" / "assess-adoption" / "SKILL.md"
INSTALL = REPO_ROOT / "tools" / "install.py"


def _tree_fingerprint(root: Path) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    if not root.exists():
        return fingerprints
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            fingerprints[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprints


def _run_assess(target: Path, *extra: str) -> subprocess.CompletedProcess:
    command = [sys.executable, str(ASSESS), "--target", str(target), *extra]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _engagement_resolutions(**extra: dict) -> dict:
    findings = {
        "engagement.exclusive_governance": {"resolution_status": "remap"},
        "engagement.human_authorities": {"resolution_status": "remap"},
    }
    findings.update(extra)
    return {"findings": findings}


def test_ado_ac_001_target_without_framework_untouched(tmp_path: Path) -> None:
    target = tmp_path / "plain"
    target.mkdir()
    (target / "README.md").write_text("# app\n", encoding="utf-8")
    before = _tree_fingerprint(target)

    result = _run_assess(target, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["kind"] == REPORT_KIND
    assert report["verdict"] == "no_go"
    assert before == _tree_fingerprint(target)


def test_ado_ac_002_cursor_collision_detected_without_mutation(tmp_path: Path) -> None:
    target = tmp_path / "cursor-collision"
    target.mkdir()
    cursor = target / ".cursor"
    cursor.mkdir()
    cli = cursor / "cli.json"
    original = '{"sentinel": true}\n'
    cli.write_text(original, encoding="utf-8")
    before = _tree_fingerprint(target)

    result = _run_assess(target, "--json")
    assert result.returncode == 2
    report = json.loads(result.stdout)
    ids = {item["id"] for item in report["findings"]}
    assert "artifact.cursor_cli_json" in ids
    assert "artifact.cursor_tree" in ids
    assert cli.read_text(encoding="utf-8") == original
    assert before == _tree_fingerprint(target)


def test_ado_ac_003_no_go_when_blocking_unresolved() -> None:
    findings = [
        Finding(
            id="x",
            category="engagement",
            severity="blocking",
            summary="open",
            evidence={},
            resolution_status="unresolved",
        )
    ]
    assert compute_verdict(findings) == "no_go"
    findings[0].resolution_status = "defer_blocks_adoption"
    assert compute_verdict(findings) == "no_go"


def test_ado_ac_004_go_when_blocking_resolved(tmp_path: Path) -> None:
    target = tmp_path / "ready"
    target.mkdir()
    report = run_assessment(target, resolutions=_engagement_resolutions())
    assert report["verdict"] in {"go", "go_with_backlog"}
    for item in report["findings"]:
        if item["severity"] != "blocking":
            continue
        finding = Finding(
            id=item["id"],
            category=item["category"],
            severity=item["severity"],
            summary=item["summary"],
            evidence=item["evidence"],
            resolution_options=item["resolution_options"],
            resolution_status=item["resolution_status"],
            waiver_authorization_id=item.get("waiver_authorization_id"),
            operator_confirmation_required=item.get("operator_confirmation_required", False),
        )
        assert blocking_is_resolved(finding)


def test_ado_ac_004_go_with_backlog_when_warning_open(tmp_path: Path) -> None:
    target = tmp_path / "warn"
    target.mkdir()
    (target / "AGENTS.md").write_text("# custom\n", encoding="utf-8")
    report = run_assessment(target, resolutions=_engagement_resolutions())
    assert report["verdict"] == "go_with_backlog"
    assert any(item["id"] == "artifact.agents_md" for item in report["backlog"])


def test_ado_ac_005_all_categories_present(tmp_path: Path) -> None:
    target = tmp_path / "brownfield"
    target.mkdir()
    (target / "src").mkdir()
    (target / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    (target / ".cursor").mkdir()
    (target / ".cursor" / "cli.json").write_text("{}\n", encoding="utf-8")
    (target / "AGENTS.md").write_text("x\n", encoding="utf-8")
    report = run_assessment(target)
    for category in CATEGORIES:
        assert category in report["categories"]
        assert report["categories"][category]["empty"] is False
        assert report["categories"][category]["findings"]


def test_ado_ac_006_no_hybrid_option(tmp_path: Path) -> None:
    target = tmp_path / "hybrid"
    target.mkdir()
    result = _run_assess(target, "--json")
    report = json.loads(result.stdout)
    assert report["notes"]["hybrid_mode_supported"] is False
    assert "hybrid" not in " ".join(DEFAULT_RESOLUTION_OPTIONS).lower()
    human = _run_assess(target)
    assert "Hybrid governance is not a supported option" in human.stdout
    assert "defer_blocks_adoption" in human.stdout


def test_ado_ac_007_cli_help_distinguishes_roles() -> None:
    result = subprocess.run(
        [sys.executable, str(ASSESS), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "preflight" in help_text
    assert "diagnose" in help_text
    assert "g0" in help_text
    assert "hybrid" in help_text


def test_ado_ac_008_waive_without_trace_still_blocking() -> None:
    finding = Finding(
        id="artifact.cursor_tree",
        category="artifact",
        severity="blocking",
        summary="cursor",
        evidence={},
        resolution_status="waive",
        waiver_authorization_id=None,
    )
    assert blocking_is_resolved(finding) is False
    assert compute_verdict([finding]) == "no_go"
    finding.waiver_authorization_id = "AUTH-1"
    assert blocking_is_resolved(finding) is True
    assert compute_verdict([finding]) == "go"


def test_ado_ac_009_assessment_leaves_brownfield_code_intact(tmp_path: Path) -> None:
    target = tmp_path / "brownfield"
    target.mkdir()
    (target / "README.md").write_text("# My App\n", encoding="utf-8")
    (target / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (target / "src").mkdir()
    (target / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")
    (target / "docs").mkdir()
    (target / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")
    before = _tree_fingerprint(target)

    result = _run_assess(target, "--json")
    assert result.returncode == 2
    assert before == _tree_fingerprint(target)
    assert (target / "README.md").read_text(encoding="utf-8") == "# My App\n"
    assert (target / "src" / "app.py").read_text(encoding="utf-8") == "print('app')\n"


def test_ado_ac_010_adopter_docs_describe_sequence() -> None:
    guide = (REPO_ROOT / "docs" / "adopter-guide" / "adoption-assessment.md").read_text(
        encoding="utf-8"
    )
    checklist = (REPO_ROOT / "docs" / "adopter-guide" / "adopter-checklist.md").read_text(
        encoding="utf-8"
    )
    assert "Assessment" in guide or "assessment" in guide
    assert "G0" in guide
    assert "tools/assess.py" in guide or "assess" in guide.lower()
    assert "Assessment" in checklist or "assessment" in checklist
    assert "no_go" in guide
    assert "as-built" in guide.lower() or "as_built" in guide.lower() or "baseline" in guide
    assert "2bis" in checklist or "as-built" in checklist.lower() or "Baseline" in checklist


def test_assess_adoption_slash_facade_is_source_only_and_read_only() -> None:
    skill = ASSESS_SKILL.read_text(encoding="utf-8")
    assert "name: assess-adoption" in skill
    assert "disable-model-invocation: true" in skill
    assert "python tools/assess.py --target <target-path>" in skill
    assert "read-only" in skill
    assert "Do not install" in skill
    assert "/reconcile-project" in skill
    assert not (
        REPO_ROOT
        / "adapters"
        / "cursor"
        / "templates"
        / ".cursor"
        / "skills"
        / "assess-adoption"
    ).exists()


def test_ado_ac_011_baseline_brownfield_without_product_docs(tmp_path: Path) -> None:
    target = tmp_path / "legacy-app"
    target.mkdir()
    (target / "src").mkdir()
    (target / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    report = run_assessment(target, resolutions=_engagement_resolutions())
    ids = {item["id"] for item in report["findings"]}
    assert "baseline.as_built_inventory" in ids
    assert "baseline.product_material_gap" in ids
    assert "baseline.human_material_before_compile" in ids
    assert report["verdict"] == "go_with_backlog"
    backlog_ids = {item["id"] for item in report["backlog"]}
    assert "baseline.as_built_inventory" in backlog_ids
    assert "baseline.product_material_gap" in backlog_ids

    resolved = run_assessment(
        target,
        resolutions=_engagement_resolutions(
            **{
                "baseline.as_built_inventory": {"resolution_status": "remap"},
                "baseline.product_material_gap": {"resolution_status": "remap"},
                "baseline.human_material_before_compile": {"resolution_status": "remap"},
            }
        ),
    )
    assert resolved["verdict"] in {"go", "go_with_backlog"}
    backlog_ids = {item["id"] for item in resolved["backlog"]}
    assert "baseline.as_built_inventory" not in backlog_ids
    assert "baseline.product_material_gap" not in backlog_ids
    assert "baseline.human_material_before_compile" not in backlog_ids
    assert "baseline" in resolved["categories"]
    assert resolved["categories"]["baseline"]["empty"] is False


def test_baseline_greenfield_has_material_commitment(tmp_path: Path) -> None:
    target = tmp_path / "empty"
    target.mkdir()
    report = run_assessment(target)
    ids = {item["id"] for item in report["findings"]}
    assert "baseline.greenfield_or_minimal_code" in ids
    assert "baseline.human_material_before_compile" in ids
    assert "baseline.as_built_inventory" not in ids
    assert "baseline.product_material_gap" not in ids


def test_report_file_written_outside_target(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.mkdir()
    report_path = tmp_path / "out" / "report.json"
    before = _tree_fingerprint(target)
    result = _run_assess(target, "--json", "--report-file", str(report_path))
    assert result.returncode == 2
    assert report_path.is_file()
    assert before == _tree_fingerprint(target)
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["verdict"] == "no_go"


def test_assessment_gate_requires_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ASSESSMENT_SKIP_ENV, raising=False)
    err = assessment_gate_error(assessment_report=None, skip_assessment_gate=False)
    assert err is not None
    assert "--assessment-report" in err


def test_fresh_install_accepts_go_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ASSESSMENT_SKIP_ENV, raising=False)
    target = tmp_path / "install-me"
    target.mkdir()
    resolutions = tmp_path / "res.json"
    resolutions.write_text(json.dumps(_engagement_resolutions()), encoding="utf-8")
    report_path = tmp_path / "report.json"
    assess = _run_assess(target, "--json", "--resolutions", str(resolutions), "--report-file", str(report_path))
    assert assess.returncode == 0, assess.stdout + assess.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["verdict"] in {"go", "go_with_backlog"}

    env = os.environ.copy()
    env.pop(ASSESSMENT_SKIP_ENV, None)
    install = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "assessed",
            "--project-name",
            "Assessed",
            "--assessment-report",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
        env=env,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    assert (target / ".ai-team" / "installation-record.json").is_file()


def test_fresh_install_rejects_no_go_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ASSESSMENT_SKIP_ENV, raising=False)
    target = tmp_path / "blocked"
    target.mkdir()
    report_path = tmp_path / "no_go.json"
    assess = _run_assess(target, "--json", "--report-file", str(report_path))
    assert assess.returncode == 2
    env = os.environ.copy()
    env.pop(ASSESSMENT_SKIP_ENV, None)
    install = subprocess.run(
        [
            sys.executable,
            str(INSTALL),
            "--target",
            str(target),
            "--project-id",
            "blocked",
            "--project-name",
            "Blocked",
            "--assessment-report",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
        env=env,
    )
    assert install.returncode == 2
    assert "no_go" in install.stdout
    assert not (target / ".ai-team" / "installation-record.json").exists()
