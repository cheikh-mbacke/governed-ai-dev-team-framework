"""WU-P4-SHADOW-COMPILE — install path uses Cursor compiler by default."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALL = ROOT / "tools" / "install.py"
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "cursor-compile" / "golden-manifest.json"


class InstallCompilerTests(unittest.TestCase):
    def test_fresh_install_materializes_compiled_cursor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cursor-install-") as temp_dir:
            target = Path(temp_dir) / "proj"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(INSTALL),
                    "--target",
                    str(target),
                    "--project-id",
                    "compiler-install-test",
                    "--project-name",
                    "Compiler Install Test",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(
                proc.returncode,
                0,
                msg=proc.stdout + proc.stderr,
            )
            cursor = target / ".cursor"
            self.assertTrue(cursor.is_dir())
            self.assertTrue((cursor / "hooks.json").is_file())
            profile = (target / ".ai-team" / "project-profile.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("compiler-install-test", profile)

            golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
            expected = {entry["path"]: entry["sha256"] for entry in golden["artifacts"]}
            for rel, digest in expected.items():
                path = target / rel
                self.assertTrue(path.is_file(), rel)
                from adapters.cursor.compiler.staging import sha256_bytes

                self.assertEqual(
                    sha256_bytes(path.read_bytes()),
                    digest,
                    rel,
                )

    def test_framework_profile_declares_fabrication_mode(self) -> None:
        profile = (ROOT / ".fabric" / "project-profile.yaml").read_text(encoding="utf-8")
        self.assertIn("repository_kind: framework_source", profile)
        self.assertIn("fabrication_workflow: classical", profile)
        self.assertIn("cursor_compile_opt_in: false", profile)


if __name__ == "__main__":
    unittest.main()
