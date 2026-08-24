#!/usr/bin/env python3
from pathlib import Path
import sys
import json
import subprocess

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    print("Missing dependency: PyYAML and/or jsonschema. Install them first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"

errors = []
warnings = []

required = [
    AI / "project-profile.yaml",
    AI / "constitution" / "constitution.yaml",
    AI / "sources" / "source-registry.yaml",
    AI / "state" / "project-state.yaml",
    ROOT / ".cursor" / "hooks.json",
    ROOT / ".cursor" / "hooks" / "run_hook.cmd",
    ROOT / ".cursor" / "permissions.json",
    ROOT / ".cursor" / "cli.json",
]
for p in required:
    if not p.exists():
        errors.append(f"Missing required file: {p.relative_to(ROOT)}")


def load_yaml(p):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"Invalid YAML {p.relative_to(ROOT)}: {e}")
        return None


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"Invalid JSON {p.relative_to(ROOT)}: {e}")
        return None


cursor_dir = ROOT / ".cursor"
for cursor_json_name in ["hooks.json", "permissions.json"]:
    cursor_json_path = cursor_dir / cursor_json_name
    if cursor_json_path.exists():
        load_json(cursor_json_path)

cli_config_path = cursor_dir / "cli.json"
if cli_config_path.exists():
    cli_config = load_json(cli_config_path)
    if cli_config is not None:
        unsupported_project_settings = sorted(set(cli_config) - {"permissions"})
        if unsupported_project_settings:
            errors.append(
                ".cursor/cli.json: only permissions can be configured at project level; "
                "move these settings to ~/.cursor/cli-config.json or /config: "
                + ", ".join(unsupported_project_settings)
            )
        permissions = cli_config.get("permissions")
        if not isinstance(permissions, dict):
            errors.append(".cursor/cli.json: permissions must be an object")
        else:
            for permission_kind in ["allow", "deny"]:
                entries = permissions.get(permission_kind)
                if not isinstance(entries, list) or not all(
                    isinstance(entry, str) for entry in entries
                ):
                    errors.append(
                        f".cursor/cli.json: permissions.{permission_kind} must be a list "
                        "of strings"
                    )

if (AI / "project-profile.yaml").exists():
    profile = load_yaml(AI / "project-profile.yaml") or {}
    if profile.get("setup_status", {}).get("template"):
        warnings.append("project-profile.yaml is still marked as template=true")
    for field in ["build", "lint", "unit_test"]:
        if profile.get("commands", {}).get(field) is None:
            warnings.append(f"Project command '{field}' is not configured")
    auth = profile.get("human_authorities", {})
    for k, v in auth.items():
        if v in (None, "unspecified", ""):
            warnings.append(f"Human authority '{k}' is unspecified")

    protected_branch = profile.get("release", {}).get("protected_branch")
    if protected_branch and (ROOT / ".git").exists():
        try:
            existing_branches = subprocess.run(
                ["git", "branch", "--list", "--format=%(refname:short)"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            ).stdout.split()
            if existing_branches and protected_branch not in existing_branches:
                warnings.append(
                    f"release.protected_branch is '{protected_branch}' but no such git "
                    f"branch exists here (found: {', '.join(existing_branches)}). Branch "
                    "protection in hooks and CI can only recognize a branch it can name "
                    "correctly - fix one side to match the other (see README.md 'Important "
                    "security note')."
                )
        except Exception:
            pass  # Best-effort check; never fail validate.py over git introspection.

if (AI / "sources" / "source-registry.yaml").exists():
    reg = load_yaml(AI / "sources" / "source-registry.yaml") or {}
    if not reg.get("sources"):
        warnings.append("No authoritative product sources are registered")

schema_dir = AI / "schemas"

def validate_instance(instance_path, schema_name):
    data = load_yaml(instance_path)
    if data is None:
        return
    schema_path = schema_dir / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for err in Draft202012Validator(schema).iter_errors(data):
        errors.append(f"{instance_path.relative_to(ROOT)}: {'/'.join(map(str, err.path))}: {err.message}")


# Validate framework metadata objects
if (AI / "project-profile.yaml").exists():
    validate_instance(AI / "project-profile.yaml", "project-profile.schema.json")
if (AI / "sources" / "source-registry.yaml").exists():
    validate_instance(AI / "sources" / "source-registry.yaml", "source-registry.schema.json")
    registry = load_yaml(AI / "sources" / "source-registry.yaml") or {}
    for src in registry.get("sources") or []:
        if src.get("path") and src.get("status") == "active":
            sp = ROOT / src["path"]
            if not sp.exists():
                warnings.append(f"Registered source path does not exist: {src['path']}")

state_path = AI / "state" / "project-state.yaml"
if state_path.exists():
    validate_instance(state_path, "project-state.schema.json")

for p in sorted((AI / "work-units").glob("*.yaml")):
    validate_instance(p, "work-unit.schema.json")
for p in sorted((AI / "events").glob("*.yaml")):
    validate_instance(p, "event.schema.json")
for p in sorted((AI / "evidence").glob("*.yaml")):
    validate_instance(p, "evidence.schema.json")
for p in sorted((AI / "findings").glob("*.yaml")):
    validate_instance(p, "finding.schema.json")
for p in sorted((AI / "decisions").glob("*.yaml")):
    if p.name.startswith("gate-"):
        validate_instance(p, "gate-decision.schema.json")
    else:
        validate_instance(p, "decision.schema.json")
for p in sorted((AI / "context-packages").glob("*.yaml")):
    validate_instance(p, "context-package.schema.json")
for p in sorted((AI / "acceptance").glob("*.yaml")):
    validate_instance(p, "acceptance.schema.json")
for p in sorted((AI / "releases").glob("*.yaml")):
    validate_instance(p, "release-candidate.schema.json")

print("Governed AI Team validation")
print("=" * 28)
for w in warnings:
    print(f"WARN  {w}")
for e in errors:
    print(f"ERROR {e}")
print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
sys.exit(1 if errors else 0)
