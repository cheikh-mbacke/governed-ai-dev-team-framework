import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CURSOR = ROOT / ".cursor"


class CursorCliConfigurationTests(unittest.TestCase):
    def test_ui_and_cli_permission_profiles_coexist(self):
        ui_config = json.loads((CURSOR / "permissions.json").read_text(encoding="utf-8"))
        cli_config = json.loads((CURSOR / "cli.json").read_text(encoding="utf-8"))

        self.assertIn("autoRun", ui_config)
        self.assertEqual(set(cli_config), {"permissions"})

        allow = set(cli_config["permissions"]["allow"])
        deny = set(cli_config["permissions"]["deny"])
        self.assertIn("Shell(git:status*)", allow)
        self.assertIn("Shell(python:scripts/ai-team/diagnose.py*)", allow)
        self.assertIn("Write(.ai-team/constitution/**)", deny)
        self.assertIn("Write(.cursor/cli.json)", deny)
        self.assertIn("Shell(git:reset*--hard*)", deny)

    def test_subagents_are_foreground_by_default_and_readonly_roles_stay_readonly(self):
        readonly_roles = {
            "architect.md",
            "auditor.md",
            "code-reviewer.md",
            "product-analyst.md",
            "release-agent.md",
            "security-reviewer.md",
        }
        for agent_path in sorted((CURSOR / "agents").glob("*.md")):
            text = agent_path.read_text(encoding="utf-8")
            self.assertNotIn("is_background: true", text, agent_path.name)
            if agent_path.name in readonly_roles:
                self.assertIn("readonly: true", text, agent_path.name)

    def test_auth_smoke_agent_is_non_readonly_for_windows_allowlist_smoke(self):
        text = (CURSOR / "agents" / "auth-smoke.md").read_text(encoding="utf-8")
        self.assertIn("name: auth-smoke", text)
        self.assertIn("readonly: false", text)
        self.assertNotIn("readonly: true", text)

    def test_hooks_cover_shell_and_subagent_lifecycle(self):
        hooks = json.loads((CURSOR / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for hook_name in [
            "beforeShellExecution",
            "afterShellExecution",
            "subagentStart",
            "subagentStop",
        ]:
            self.assertIn(hook_name, hooks)
            self.assertTrue(hooks[hook_name])

    def test_hooks_invoke_python3_by_default(self):
        """WSL/Linux often lack a bare `python`; shipped hooks must use python3."""
        hooks_text = (CURSOR / "hooks.json").read_text(encoding="utf-8")
        self.assertNotIn('"command": "python ', hooks_text)
        self.assertIn('"command": "python3 ', hooks_text)


class AuditEventTests(unittest.TestCase):
    def run_audit(self, stdin_data, env=None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        if isinstance(stdin_data, str):
            stdin_data = stdin_data.encode("utf-8")
        return subprocess.run(
            [sys.executable, str(CURSOR / "hooks" / "audit_event.py")],
            input=stdin_data,
            capture_output=True,
            cwd=ROOT,
            env=merged,
            timeout=10,
        )

    def test_valid_json_payload_is_logged_intact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_audit(
                json.dumps(
                    {
                        "hook_event_name": "beforeShellExecution",
                        "command": "whoami",
                    }
                ),
                env={"CURSOR_PROJECT_DIR": temp_dir},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.decode("utf-8"))["permission"], "allow")
            log_path = Path(temp_dir) / ".ai-team" / "logs" / "cursor-events.jsonl"
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["event"]["hook_event_name"], "beforeShellExecution")
            self.assertEqual(record["event"]["command"], "whoami")

    def test_bom_prefixed_json_is_parsed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = ("\ufeff" + json.dumps({"hook_event_name": "subagentStart"})).encode(
                "utf-8"
            )
            result = self.run_audit(payload, env={"CURSOR_PROJECT_DIR": temp_dir})
            self.assertEqual(result.returncode, 0, result.stderr)
            log_path = Path(temp_dir) / ".ai-team" / "logs" / "cursor-events.jsonl"
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["event"]["hook_event_name"], "subagentStart")

    def test_invalid_json_preserves_raw_instead_of_empty_string(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_audit(
                "not-json-but-should-be-kept",
                env={"CURSOR_PROJECT_DIR": temp_dir},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            log_path = Path(temp_dir) / ".ai-team" / "logs" / "cursor-events.jsonl"
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["event"]["raw"], "not-json-but-should-be-kept")


class GuardShellTests(unittest.TestCase):
    def run_guard(self, command):
        return subprocess.run(
            [sys.executable, str(CURSOR / "hooks" / "guard_shell.py")],
            input=json.dumps({"command": command}),
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=10,
        )

    def test_safe_command_is_allowed(self):
        result = self.run_guard("git status --short")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["permission"], "allow")

    def test_hazardous_commands_are_denied(self):
        for command in [
            "git reset --hard HEAD~1",
            "git push origin main",
            "terraform destroy",
            "kubectl delete deployment app",
            "rm -rf /",
        ]:
            with self.subTest(command=command):
                result = self.run_guard(command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["permission"], "deny")


class InstallerCliIntegrationTests(unittest.TestCase):
    def run_command(self, args, cwd=ROOT):
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_install_update_and_validation_keep_both_cursor_modes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            install = self.run_command(
                [
                    sys.executable,
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--project-id",
                    "cli-test",
                    "--project-name",
                    "CLI Test",
                ]
            )
            self.assertEqual(install.returncode, 0, install.stderr + install.stdout)
            self.assertTrue((target / ".cursor" / "permissions.json").is_file())
            self.assertTrue((target / ".cursor" / "cli.json").is_file())

            validate = self.run_command(
                [sys.executable, "scripts/ai-team/validate.py"], cwd=target
            )
            self.assertEqual(validate.returncode, 0, validate.stderr + validate.stdout)

            profile_path = target / ".ai-team" / "project-profile.yaml"
            profile_before_update = profile_path.read_text(encoding="utf-8")
            cli_path = target / ".cursor" / "cli.json"
            cli_config = json.loads(cli_path.read_text(encoding="utf-8"))
            cli_config["permissions"]["allow"].append("Shell(test-local-override)")
            cli_path.write_text(json.dumps(cli_config), encoding="utf-8")

            update = self.run_command(
                [
                    sys.executable,
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--project-id",
                    "ignored-on-update",
                    "--project-name",
                    "Ignored On Update",
                    "--update",
                ]
            )
            self.assertEqual(update.returncode, 0, update.stderr + update.stdout)
            self.assertEqual(profile_path.read_text(encoding="utf-8"), profile_before_update)
            updated_cli = json.loads(cli_path.read_text(encoding="utf-8"))
            self.assertNotIn(
                "Shell(test-local-override)", updated_cli["permissions"]["allow"]
            )
            self.assertTrue((target / ".cursor" / "permissions.json").is_file())

    def test_validation_rejects_global_only_settings_in_project_cli_config(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            install = self.run_command(
                [
                    sys.executable,
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--project-id",
                    "global-setting-test",
                    "--project-name",
                    "Global Setting Test",
                ]
            )
            self.assertEqual(install.returncode, 0, install.stderr + install.stdout)
            cli_path = target / ".cursor" / "cli.json"
            cli_config = json.loads(cli_path.read_text(encoding="utf-8"))
            cli_config["approvalMode"] = "allowlist"
            cli_path.write_text(json.dumps(cli_config), encoding="utf-8")

            validate = self.run_command(
                [sys.executable, "scripts/ai-team/validate.py"], cwd=target
            )
            self.assertEqual(validate.returncode, 1)
            self.assertIn("only permissions can be configured at project level", validate.stdout)

    def test_validation_rejects_malformed_cli_configuration(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            install = self.run_command(
                [
                    sys.executable,
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--project-id",
                    "invalid-cli-test",
                    "--project-name",
                    "Invalid CLI Test",
                ]
            )
            self.assertEqual(install.returncode, 0, install.stderr + install.stdout)
            (target / ".cursor" / "cli.json").write_text("{not-json", encoding="utf-8")

            validate = self.run_command(
                [sys.executable, "scripts/ai-team/validate.py"], cwd=target
            )
            self.assertEqual(validate.returncode, 1)
            self.assertIn("Invalid JSON .cursor", validate.stdout)


if __name__ == "__main__":
    unittest.main()
