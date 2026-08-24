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
        self.assertIn("Shell(py:-3 scripts/ai-team/preflight.py*)", allow)
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

    def test_auth_smoke_agent_is_non_readonly_for_cross_platform_allowlist_smoke(self):
        text = (CURSOR / "agents" / "auth-smoke.md").read_text(encoding="utf-8")
        self.assertIn("name: auth-smoke", text)
        self.assertIn("readonly: false", text)
        self.assertNotIn("readonly: true", text)
        self.assertIn("Cross-platform CLI Allowlist", text)

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

    def test_hooks_use_portable_python_runner(self):
        hooks = json.loads((CURSOR / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        commands = [item["command"] for definitions in hooks.values() for item in definitions]
        self.assertTrue(commands)
        for command in commands:
            self.assertTrue(
                command.startswith(".cursor/hooks/run_hook.cmd "), command
            )

        runner = (CURSOR / "hooks" / "run_hook.cmd").read_text(encoding="utf-8")
        for candidate in ["python3", "python", "py -3"]:
            self.assertIn(candidate, runner)


class PortableHookRunnerTests(unittest.TestCase):
    def run_guard(self, command):
        return subprocess.run(
            ".cursor/hooks/run_hook.cmd .cursor/hooks/guard_shell.py",
            input=json.dumps({"command": command}),
            text=True,
            capture_output=True,
            cwd=ROOT,
            shell=True,
            timeout=10,
        )

    def test_runner_executes_safe_hook(self):
        result = self.run_guard("whoami")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["permission"], "allow")

    def test_runner_preserves_hook_denial_exit_code(self):
        result = self.run_guard("git reset --hard HEAD")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["permission"], "deny")

    @unittest.skipIf(os.name == "nt", "POSIX fallback branch only")
    def test_posix_runner_falls_back_to_python_when_python3_is_absent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            interpreter = Path(temp_dir) / "python"
            interpreter.symlink_to(sys.executable)
            env = os.environ.copy()
            env["PATH"] = temp_dir
            result = subprocess.run(
                ".cursor/hooks/run_hook.cmd .cursor/hooks/guard_shell.py",
                input=json.dumps({"command": "whoami"}),
                text=True,
                capture_output=True,
                cwd=ROOT,
                env=env,
                shell=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["permission"], "allow")


class PreflightTests(unittest.TestCase):
    def test_preflight_reports_machine_readable_capabilities(self):
        result = subprocess.run(
            [sys.executable, "scripts/ai-team/preflight.py", "--json"],
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=15,
        )
        self.assertIn(result.returncode, {0, 1}, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["hooks_config"]["status"], "pass")
        self.assertEqual(report["guard_hook"]["status"], "pass")
        self.assertEqual(report["project_cli"]["status"], "pass")
        self.assertEqual(report["global_allowlist"]["status"], "manual")
        self.assertEqual(report["execution_surface"]["status"], "manual")
        if report["platform"] == "windows-native":
            self.assertEqual(report["readonly_sandbox"]["status"], "skip")
        else:
            self.assertEqual(report["readonly_sandbox"]["status"], "expected")


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

    def initialize_git(self, target):
        commands = [
            ["git", "init", "-q"],
            ["git", "config", "user.name", "Framework Test"],
            ["git", "config", "user.email", "framework-test@example.invalid"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "test fixture"],
        ]
        for command in commands:
            result = self.run_command(command, cwd=target)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def install_target(self, target, project_id="cli-test", project_name="CLI Test"):
        install = self.run_command(
            [
                sys.executable,
                "tools/install.py",
                "--target",
                str(target),
                "--project-id",
                project_id,
                "--project-name",
                project_name,
            ]
        )
        self.assertEqual(install.returncode, 0, install.stderr + install.stdout)
        return install

    def test_install_update_and_validation_keep_both_cursor_modes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            self.assertTrue((target / ".cursor" / "permissions.json").is_file())
            self.assertTrue((target / ".cursor" / "cli.json").is_file())
            installed_runner = target / ".cursor" / "hooks" / "run_hook.cmd"
            self.assertTrue(installed_runner.is_file())
            if os.name != "nt":
                self.assertTrue(os.access(installed_runner, os.X_OK))
            self.assertTrue((target / "scripts" / "ai-team" / "preflight.py").is_file())

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
            self.initialize_git(target)

            update = self.run_command(
                [
                    sys.executable,
                    "tools/install.py",
                    "--target",
                    str(target),
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
            manifest = json.loads(
                (target / ".ai-team" / "framework-version.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["version"], "0.2.0")
            self.assertIn(".cursor/hooks.json", manifest["managed_files"])

    def test_validation_rejects_global_only_settings_in_project_cli_config(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target, "global-setting-test", "Global Setting Test")
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
            self.install_target(target, "invalid-cli-test", "Invalid CLI Test")
            (target / ".cursor" / "cli.json").write_text("{not-json", encoding="utf-8")

            validate = self.run_command(
                [sys.executable, "scripts/ai-team/validate.py"], cwd=target
            )
            self.assertEqual(validate.returncode, 1)
            self.assertIn("Invalid JSON .cursor", validate.stdout)

    def test_update_dry_run_is_read_only_even_without_site_packages(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            cli_path = target / ".cursor" / "cli.json"
            before = cli_path.read_bytes()
            result = self.run_command(
                [
                    sys.executable,
                    "-S",
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--update",
                    "--dry-run",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("DRY-RUN: no file was modified", result.stdout)
            self.assertEqual(cli_path.read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "WSL/Linux target-venv selection test")
    def test_update_started_without_site_packages_uses_target_venv_for_validation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            marker = target / ".ai-team" / "framework-version.json"
            marker.unlink()
            target_python = target / ".venv" / "bin" / "python"
            target_python.parent.mkdir(parents=True)
            target_python.write_text(
                f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8"
            )
            target_python.chmod(0o755)
            self.initialize_git(target)

            result = self.run_command(
                [
                    sys.executable,
                    "-S",
                    "tools/install.py",
                    "--target",
                    str(target),
                    "--update",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Post-update validation: PASS", result.stdout)
            self.assertTrue(marker.is_file())

    def test_update_aborts_on_dirty_target_before_writing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            self.initialize_git(target)
            cli_path = target / ".cursor" / "cli.json"
            original = cli_path.read_text(encoding="utf-8")
            cli_path.write_text(original + "\n", encoding="utf-8")
            result = self.run_command(
                [sys.executable, "tools/install.py", "--target", str(target), "--update"]
            )
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            self.assertIn("target must be a clean", result.stdout)
            self.assertEqual(cli_path.read_text(encoding="utf-8"), original + "\n")

    def test_update_rejects_unknown_future_version_before_writing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            marker = target / ".ai-team" / "framework-version.json"
            payload = json.loads(marker.read_text(encoding="utf-8"))
            payload["version"] = "99.0.0"
            marker.write_text(json.dumps(payload), encoding="utf-8")
            cli_path = target / ".cursor" / "cli.json"
            cli_before = cli_path.read_bytes()
            self.initialize_git(target)

            result = self.run_command(
                [sys.executable, "tools/install.py", "--target", str(target), "--update"]
            )
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            self.assertIn("No safe migration path", result.stdout)
            self.assertEqual(cli_path.read_bytes(), cli_before)
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))["version"], "99.0.0"
            )

    def test_legacy_update_migrates_acceptance_and_keeps_backup(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            (target / ".ai-team" / "framework-version.json").unlink()
            acceptance = target / ".ai-team" / "acceptance" / "ACC-LEGACY.yaml"
            acceptance.write_text(
                "id: ACC-LEGACY\nscenarios: []\nhuman_result:\n  status: accepted\n",
                encoding="utf-8",
            )
            cli_path = target / ".cursor" / "cli.json"
            cli_config = json.loads(cli_path.read_text(encoding="utf-8"))
            cli_config["permissions"]["allow"].append("Shell(legacy-override)")
            cli_path.write_text(json.dumps(cli_config), encoding="utf-8")
            self.initialize_git(target)

            result = self.run_command(
                [sys.executable, "tools/install.py", "--target", str(target), "--update"]
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Post-update validation: PASS", result.stdout)
            self.assertIn("status: passed", acceptance.read_text(encoding="utf-8"))
            backup = (
                target
                / ".ai-team"
                / "migration-backups"
                / "acceptance-status-passed"
                / ".ai-team"
                / "acceptance"
                / "ACC-LEGACY.yaml"
            )
            self.assertIn("status: accepted", backup.read_text(encoding="utf-8"))
            updated_cli = json.loads(cli_path.read_text(encoding="utf-8"))
            self.assertNotIn("Shell(legacy-override)", updated_cli["permissions"]["allow"])
            manifest = json.loads(
                (target / ".ai-team" / "framework-version.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["version"], "0.2.0")

    def test_failed_post_update_validation_rolls_back_all_touched_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir) / "target-project"
            self.install_target(target)
            marker = target / ".ai-team" / "framework-version.json"
            marker.unlink()
            acceptance = target / ".ai-team" / "acceptance" / "ACC-INVALID.yaml"
            acceptance.write_text(
                "id: ACC-INVALID\nscenarios: []\nhuman_result:\n  status: invalid\n",
                encoding="utf-8",
            )
            cli_path = target / ".cursor" / "cli.json"
            cli_config = json.loads(cli_path.read_text(encoding="utf-8"))
            cli_config["permissions"]["allow"].append("Shell(must-survive-rollback)")
            cli_path.write_text(json.dumps(cli_config), encoding="utf-8")
            self.initialize_git(target)

            result = self.run_command(
                [sys.executable, "tools/install.py", "--target", str(target), "--update"]
            )
            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("Update rolled back", result.stdout)
            self.assertFalse(marker.exists())
            rolled_back_cli = json.loads(cli_path.read_text(encoding="utf-8"))
            self.assertIn(
                "Shell(must-survive-rollback)", rolled_back_cli["permissions"]["allow"]
            )


class MigrationTests(unittest.TestCase):
    def run_migration(self, target, apply=False):
        command = [
            sys.executable,
            "scripts/ai-team/migrate.py",
            "--target",
            str(target),
        ]
        if apply:
            command.append("--apply")
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_standalone_migration_is_dry_run_then_idempotent_apply(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir)
            acceptance_dir = target / ".ai-team" / "acceptance"
            acceptance_dir.mkdir(parents=True)
            acceptance = acceptance_dir / "ACC-WU-BE-0004.yaml"
            original = (
                "id: ACC-WU-BE-0004\n"
                "scenarios: []\n"
                "human_result:\n"
                "  status: 'accepted' # legacy value\n"
            )
            acceptance.write_text(original, encoding="utf-8")

            dry_run = self.run_migration(target)
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr + dry_run.stdout)
            self.assertIn("MIGRATE", dry_run.stdout)
            self.assertEqual(acceptance.read_text(encoding="utf-8"), original)

            applied = self.run_migration(target, apply=True)
            self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)
            self.assertIn("status: 'passed' # legacy value", acceptance.read_text())
            second = self.run_migration(target, apply=True)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertIn("No project-data migration required", second.stdout)

    def test_migration_only_changes_status_inside_human_result(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            target = Path(temp_dir)
            acceptance_dir = target / ".ai-team" / "acceptance"
            acceptance_dir.mkdir(parents=True)
            acceptance = acceptance_dir / "ACC-SCOPED.yaml"
            acceptance.write_text(
                "status: accepted\n"
                "machine_result:\n"
                "  status: accepted\n"
                "human_result:\n"
                "  status: accepted\n",
                encoding="utf-8",
            )

            result = self.run_migration(target, apply=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(
                acceptance.read_text(encoding="utf-8"),
                "status: accepted\n"
                "machine_result:\n"
                "  status: accepted\n"
                "human_result:\n"
                "  status: passed\n",
            )


if __name__ == "__main__":
    unittest.main()
