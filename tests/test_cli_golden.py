"""Characterization tests: CLI exit codes and stdout/stderr vs legacy 0.4.x goldens."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from cli_golden import FIXTURES_DIR, ROOT, install_baseline_target, load_golden, run_cli


class CliGoldenCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir = tempfile.TemporaryDirectory(dir=ROOT)
        cls.target = install_baseline_target(Path(cls._temp_dir.name))

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    def assert_matches_golden(self, scenario: str, observed: dict) -> None:
        golden = load_golden(scenario)
        self.assertEqual(
            observed["exit_code"],
            golden["exit_code"],
            f"{scenario} exit code\nstdout={observed['stdout']}\nstderr={observed['stderr']}",
        )
        self.assertEqual(observed["stdout"], golden["stdout"], f"{scenario} stdout")
        self.assertEqual(observed["stderr"], golden["stderr"], f"{scenario} stderr")

    def test_install_fresh(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target"
            observed = run_cli(
                [
                    sys.executable,
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--project-id",
                    "golden-baseline",
                    "--project-name",
                    "Golden Baseline",
                ]
            )
        self.assert_matches_golden("install-fresh", observed)

    def test_install_missing_target(self):
        observed = run_cli(
            [
                sys.executable,
                "tools/install.py",
                "--project-id",
                "missing-target",
                "--project-name",
                "Missing Target",
            ]
        )
        self.assert_matches_golden("install-missing-target", observed)

    def test_validate_clean_install(self):
        observed = run_cli([sys.executable, "scripts/ai-team/validate.py"], cwd=self.target)
        self.assert_matches_golden("validate-clean", observed)

    def test_status_clean_install(self):
        observed = run_cli([sys.executable, "scripts/ai-team/status.py"], cwd=self.target)
        self.assert_matches_golden("status-clean", observed)

    def test_diagnose_clean_install(self):
        observed = run_cli([sys.executable, "scripts/ai-team/diagnose.py"], cwd=self.target)
        self.assert_matches_golden("diagnose-clean", observed)

    def test_preflight_json_clean_install(self):
        observed = run_cli(
            [sys.executable, "scripts/ai-team/preflight.py", "--json"],
            cwd=self.target,
        )
        self.assert_matches_golden("preflight-json", observed)

    def test_check_done_missing_work_unit(self):
        observed = run_cli(
            [sys.executable, "scripts/ai-team/check_done.py", "WU-NOT-FOUND"],
            cwd=self.target,
        )
        self.assert_matches_golden("check-done-missing", observed)

    def test_check_done_in_progress_work_unit(self):
        observed = run_cli(
            [sys.executable, "scripts/ai-team/check_done.py", "WU-P0-BASELINE"],
            cwd=self.target,
        )
        self.assert_matches_golden("check-done-in-progress", observed)

    def test_feedback_record_and_export(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = install_baseline_target(Path(temp_dir))
            record = run_cli(
                [
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
                cwd=target,
            )
            self.assert_matches_golden("feedback-record", record)
            export = run_cli(
                [
                    sys.executable,
                    "scripts/ai-team/feedback.py",
                    "export",
                    "--output",
                    str(target / "export.json"),
                ],
                cwd=target,
            )
        self.assert_matches_golden("feedback-export-structured", export)

    def test_baseline_manifest_lists_critical_clis(self):
        manifest = json.loads(
            (FIXTURES_DIR.parent / "baseline-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["framework_version"], "0.4.0")
        self.assertEqual(manifest["baseline_tag"], "v0.4.0-baseline")
        for tool in (
            "validate.py",
            "feedback.py",
            "check_done.py",
            "preflight.py",
            "diagnose.py",
            "status.py",
            "tools/install.py",
        ):
            self.assertIn(tool, manifest["cli_tools"])
        for scenario in (
            "install-fresh",
            "check-done-missing",
            "feedback-record",
        ):
            self.assertIn(scenario, manifest["scenarios"])


if __name__ == "__main__":
    unittest.main()
