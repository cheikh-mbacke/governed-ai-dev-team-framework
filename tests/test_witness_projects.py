"""Integration tests for clean and legacy witness project fixtures."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "projects"
CLEAN_DIR = FIXTURES_DIR / "clean"
LEGACY_DIR = FIXTURES_DIR / "legacy"
MANIFEST_PATH = FIXTURES_DIR / "witness-manifest.json"
GENERATOR = ROOT / "tests" / "generate_witness_projects.py"

OBSOLETE_MANAGED_REL = ".cursor/skills/legacy-witness-removed/SKILL.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def run_validate(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/ai-team/validate.py"],
        cwd=target,
        text=True,
        capture_output=True,
        timeout=120,
    )


class WitnessProjectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CLEAN_DIR.is_dir() or not LEGACY_DIR.is_dir():
            raise unittest.SkipTest(
                "Witness fixtures missing — run: python tests/generate_witness_projects.py --write"
            )
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_exists_with_both_trees(self):
        self.assertIn("trees", self.manifest)
        names = {tree["name"] for tree in self.manifest["trees"]}
        self.assertEqual(names, {"clean", "legacy"})

    def test_clean_witness_validates_without_errors(self):
        result = run_validate(CLEAN_DIR)
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )
        self.assertNotIn("ERROR ", result.stdout)

    def test_legacy_witness_validates_without_errors(self):
        result = run_validate(LEGACY_DIR)
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )
        self.assertNotIn("ERROR ", result.stdout)

    def test_legacy_has_runtime_artifacts(self):
        ai = LEGACY_DIR / ".ai-team"
        self.assertTrue((ai / "work-units" / "WU-WITNESS-READY.yaml").is_file())
        self.assertTrue((ai / "work-units" / "WU-WITNESS-ACTIVE.yaml").is_file())
        self.assertTrue((ai / "work-units" / "WU-WITNESS-DONE.yaml").is_file())
        self.assertTrue((ai / "events" / "EVT-20260101-100000-orchestrator-start.yaml").is_file())
        self.assertTrue((ai / "evidence" / "EV-WITNESS-DONE-001.yaml").is_file())
        self.assertTrue((ai / "observations" / "OBS-WITNESS-001.yaml").is_file())
        self.assertTrue((ai / "retrospectives" / "RET-WITNESS-001.yaml").is_file())
        self.assertTrue((ai / "decisions" / "DEC-WITNESS-001.yaml").is_file())
        self.assertTrue((ai / "findings" / "FIND-WITNESS-001.yaml").is_file())

    def test_legacy_has_obsolete_managed_file_in_manifest(self):
        obsolete = LEGACY_DIR / OBSOLETE_MANAGED_REL
        self.assertTrue(obsolete.is_file(), "Obsolete managed artifact must exist on disk")
        version = json.loads(
            (LEGACY_DIR / ".ai-team" / "framework-version.json").read_text(encoding="utf-8")
        )
        self.assertIn(OBSOLETE_MANAGED_REL, version.get("managed_files", []))

    def test_legacy_has_user_modifications(self):
        profile_text = (LEGACY_DIR / ".ai-team" / "project-profile.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("extensions:", profile_text)
        self.assertTrue((LEGACY_DIR / ".ai-team" / "user" / "local-notes.yaml").is_file())
        active_wu = (LEGACY_DIR / ".ai-team" / "work-units" / "WU-WITNESS-ACTIVE.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("USER EDIT", active_wu)

    def test_clean_has_minimal_project_state(self):
        import yaml

        state = yaml.safe_load(
            (CLEAN_DIR / ".ai-team" / "state" / "project-state.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["phase"], "not_compiled")
        self.assertEqual(state["work_units"], {})
        self.assertFalse(list((CLEAN_DIR / ".ai-team" / "work-units").glob("*.yaml")))
        self.assertFalse(list((CLEAN_DIR / ".ai-team" / "events").glob("*.yaml")))

    def test_manifest_hashes_match_committed_fixtures(self):
        tree_by_name = {tree["name"]: tree for tree in self.manifest["trees"]}
        for name, root in (("clean", CLEAN_DIR), ("legacy", LEGACY_DIR)):
            expected = {entry["path"]: entry["sha256"] for entry in tree_by_name[name]["files"]}
            for rel, digest in expected.items():
                path = root / rel
                self.assertTrue(path.is_file(), f"Missing fixture file: {name}/{rel}")
                self.assertEqual(
                    sha256_file(path),
                    digest,
                    f"Hash drift for {name}/{rel} — regenerate with generate_witness_projects.py --write",
                )

    def test_regeneration_script_verify_mode(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--verify"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )
        self.assertIn("PASS", result.stdout)

    def test_install_from_clean_reproduces_expected_structure(self):
        with tempfile.TemporaryDirectory(prefix="witness-install-") as temp_dir:
            parent = Path(temp_dir)
            target = parent / "reinstall-target"
            shutil.copytree(CLEAN_DIR, target)

            result = run_validate(target)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            clean_managed = json.loads(
                (CLEAN_DIR / ".ai-team" / "framework-version.json").read_text(encoding="utf-8")
            )["managed_files"]
            target_managed = json.loads(
                (target / ".ai-team" / "framework-version.json").read_text(encoding="utf-8")
            )["managed_files"]
            self.assertEqual(sorted(clean_managed), sorted(target_managed))

            for rel in clean_managed:
                self.assertTrue(
                    (target / rel).is_file(),
                    f"Managed file missing after copy-install: {rel}",
                )


if __name__ == "__main__":
    unittest.main()
