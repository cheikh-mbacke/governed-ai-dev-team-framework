import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class FeedbackLoopIntegrationTests(unittest.TestCase):
    def run_command(self, args, cwd):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def install_target(self, target):
        result = self.run_command(
            [
                sys.executable,
                "tools/install.py",
                "--target",
                str(target),
                "--project-id",
                "feedback-test",
                "--project-name",
                "Feedback Test",
            ],
            ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def write_work_unit(self, target):
        work_unit = {
            "id": "WU-FEEDBACK",
            "title": "Exercise feedback collection",
            "objective": {"result": "Feedback is recorded and exported"},
            "scope": {"include": ["feedback loop"], "exclude": []},
            "expected_behavior": "Commands produce schema-valid learning artifacts",
            "acceptance_criteria": ["A structured observation can be exported"],
            "dependencies": [],
            "risk": {"class": "low"},
            "required_verification": {},
            "status": "done",
            "revision": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        path = target / ".ai-team" / "work-units" / "WU-FEEDBACK.yaml"
        path.write_text(
            yaml.safe_dump(work_unit, sort_keys=False), encoding="utf-8"
        )

    def test_record_retrospective_export_and_validation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            self.write_work_unit(target)
            cli_config = json.loads(
                (target / ".cursor" / "cli.json").read_text(encoding="utf-8")
            )
            self.assertIn(
                "Shell(python:scripts/ai-team/feedback.py*)",
                cli_config["permissions"]["allow"],
            )

            record = self.run_command(
                [
                    sys.executable,
                    "scripts/ai-team/feedback.py",
                    "record",
                    "--category",
                    "context",
                    "--severity",
                    "medium",
                    "--origin",
                    "framework",
                    "--confidence",
                    "probable",
                    "--work-unit",
                    "WU-FEEDBACK",
                    "--symptom",
                    "A shared contract was missing from the context package",
                    "--blocked-minutes",
                    "15",
                    "--rework-required",
                    "--human-intervention",
                    "--evidence-ref",
                    "EVT-TEST",
                    "--recurrence-key",
                    "missing-shared-contract-context",
                ],
                target,
            )
            self.assertEqual(record.returncode, 0, record.stderr + record.stdout)
            observation_paths = list((target / ".ai-team" / "observations").glob("*.yaml"))
            self.assertEqual(len(observation_paths), 1)
            observation = yaml.safe_load(observation_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(observation["framework_version"], "0.4.0")
            self.assertEqual(observation["impact"]["blocked_minutes"], 15)

            retrospective = self.run_command(
                [
                    sys.executable,
                    "scripts/ai-team/feedback.py",
                    "retrospective",
                    "--work-unit",
                    "WU-FEEDBACK",
                ],
                target,
            )
            self.assertEqual(
                retrospective.returncode,
                0,
                retrospective.stderr + retrospective.stdout,
            )
            retrospective_path = next(
                (target / ".ai-team" / "retrospectives").glob("*.yaml")
            )
            snapshot = yaml.safe_load(retrospective_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["observation_summary"]["by_category"], {"context": 1})
            self.assertEqual(snapshot["signals"]["blocked_minutes"], 15)

            structured_path = target / "structured-feedback.json"
            export = self.run_command(
                [
                    sys.executable,
                    "scripts/ai-team/feedback.py",
                    "export",
                    "--output",
                    str(structured_path),
                ],
                target,
            )
            self.assertEqual(export.returncode, 0, export.stderr + export.stdout)
            structured = json.loads(structured_path.read_text(encoding="utf-8"))
            self.assertNotIn("project_id", structured)
            self.assertNotIn("symptom", structured["observations"][0])
            self.assertNotEqual(
                structured["observations"][0]["recurrence_ref"],
                "missing-shared-contract-context",
            )

            full_path = target / "full-feedback.json"
            full_export = self.run_command(
                [
                    sys.executable,
                    "scripts/ai-team/feedback.py",
                    "export",
                    "--detail-level",
                    "full",
                    "--output",
                    str(full_path),
                    "--authorization-id",
                    "HAUTH-feedback-export-test",
                ],
                target,
            )
            self.assertEqual(
                full_export.returncode,
                0,
                full_export.stderr + full_export.stdout,
            )
            full = json.loads(full_path.read_text(encoding="utf-8"))
            self.assertNotIn("project_id", full["observations"][0])
            self.assertIn("project_ref", full["observations"][0])
            self.assertIn("shared contract", full["observations"][0]["symptom"])

            validation = self.run_command(
                [sys.executable, "scripts/ai-team/validate.py"], target
            )
            self.assertEqual(
                validation.returncode, 0, validation.stderr + validation.stdout
            )

            status = self.run_command(
                [sys.executable, "scripts/ai-team/status.py"], target
            )
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            self.assertIn("Constats d'apprentissage ouverts : 1", status.stdout)
            self.assertIn("par categorie : context=1", status.stdout)

    def test_validation_rejects_malformed_observation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            malformed = target / ".ai-team" / "observations" / "OBS-BAD.yaml"
            malformed.write_text("id: OBS-BAD\ncategory: context\n", encoding="utf-8")

            validation = self.run_command(
                [sys.executable, "scripts/ai-team/validate.py"], target
            )
            self.assertEqual(validation.returncode, 1)
            self.assertIn("observations", validation.stdout)
            self.assertIn("recorded_at", validation.stdout)


if __name__ == "__main__":
    unittest.main()
