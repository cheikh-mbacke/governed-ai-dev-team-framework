#!/usr/bin/env python3
"""Regenerate legacy 0.4.x CLI golden fixtures (run once per baseline revision)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from cli_golden import FIXTURES_DIR, ROOT, install_baseline_target, normalize_cli_output, run_cli

BASELINE_META = {
    "framework_version": "0.4.0",
    "baseline_tag": "v0.4.0-baseline",
    "platform": sys.platform,
}


def write_fixture(name: str, observed: dict) -> None:
    payload = {**BASELINE_META, "scenario": name, **observed}
    path = FIXTURES_DIR / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.name} exit={observed['exit_code']}")


def main() -> int:
    scenarios: dict[str, dict] = {}

    with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
        parent = Path(temp_dir)
        target = install_baseline_target(parent)

        install_result = subprocess.run(
            [
                sys.executable,
                "tools/install.py",
                "--target",
                str(parent / "golden-target-2"),
                "--project-id",
                "golden-baseline",
                "--project-name",
                "Golden Baseline",
                "--skip-assessment-gate",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
        )
        scenarios["install-fresh"] = {
            "exit_code": install_result.returncode,
            "stdout": normalize_cli_output(install_result.stdout),
            "stderr": normalize_cli_output(install_result.stderr),
        }

        target_commands = {
            "validate-clean": [sys.executable, "scripts/ai-team/validate.py"],
            "status-clean": [sys.executable, "scripts/ai-team/status.py"],
            "diagnose-clean": [sys.executable, "scripts/ai-team/diagnose.py"],
            "preflight-json": [sys.executable, "scripts/ai-team/preflight.py", "--json"],
            "check-done-missing": [
                sys.executable,
                "scripts/ai-team/check_done.py",
                "WU-NOT-FOUND",
            ],
            "check-done-in-progress": [
                sys.executable,
                "scripts/ai-team/check_done.py",
                "WU-P0-BASELINE",
            ],
            "feedback-record": [
                sys.executable,
                "scripts/ai-team/feedback.py",
                "record",
                "--category",
                "tooling",
                "--severity",
                "low",
                "--origin",
                "framework",
                "--confidence",
                "low",
                "--symptom",
                "golden baseline capture",
            ],
        }
        for name, command in target_commands.items():
            scenarios[name] = run_cli(command, cwd=target)

        export_path = target / "export.json"
        scenarios["feedback-export-structured"] = run_cli(
            [
                sys.executable,
                "scripts/ai-team/feedback.py",
                "export",
                "--output",
                str(export_path),
            ],
            cwd=target,
        )

    scenarios["install-missing-target"] = run_cli(
        [
            sys.executable,
            "tools/install.py",
            "--project-id",
            "missing-target",
            "--project-name",
            "Missing Target",
        ]
    )

    for name, observed in scenarios.items():
        write_fixture(name, observed)

    manifest = {
        **BASELINE_META,
        "scenarios": sorted(scenarios.keys()),
        "cli_tools": [
            "validate.py",
            "feedback.py",
            "check_done.py",
            "preflight.py",
            "diagnose.py",
            "reconcile_project.py",
            "status.py",
            "tools/install.py",
        ],
    }
    manifest_path = FIXTURES_DIR.parent / "baseline-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
