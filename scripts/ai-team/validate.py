#!/usr/bin/env python3
from pathlib import Path
import sys
import json
import subprocess

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    print(
        "Missing dependency: PyYAML and/or jsonschema. "
        "Install them first, then re-run this command:"
    )
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
    AI / "framework-version.json",
    ROOT / ".cursor" / "hooks.json",
    ROOT / ".cursor" / "hooks" / "run_hook.cmd",
    ROOT / ".cursor" / "permissions.json",
    ROOT / ".cursor" / "cli.json",
    ROOT / "scripts" / "ai-team" / "migrate.py",
    ROOT / "scripts" / "ai-team" / "feedback.py",
    ROOT / "scripts" / "ai-team" / "feedback_common.py",
    AI / "schemas" / "observation.schema.json",
    AI / "schemas" / "retrospective.schema.json",
    AI / "schemas" / "feedback-export.schema.json",
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

version_path = AI / "framework-version.json"
if version_path.exists():
    version_manifest = load_json(version_path)
    if version_manifest is not None:
        if not isinstance(version_manifest.get("version"), str):
            errors.append(".ai-team/framework-version.json: version must be a string")
        managed_files = version_manifest.get("managed_files")
        if managed_files is not None and (
            not isinstance(managed_files, list)
            or not all(isinstance(path, str) for path in managed_files)
        ):
            errors.append(
                ".ai-team/framework-version.json: managed_files must be a list of strings"
            )

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
        location = "/".join(map(str, err.path))
        errors.append(f"{instance_path.relative_to(ROOT)}: {location}: {err.message}")


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

# Cross-check: a Work Unit marked done/accepted in project-state.yaml must be
# backed by a matching work-unit file and by the artifacts it references.
# validate_instance() above only checks each file's own schema; it cannot
# catch project-state.yaml claiming a completion that the WU's own record,
# events, or evidence never actually reached.
if state_path.exists():
    state = load_yaml(state_path) or {}
    wu_files = {p.stem: p for p in (AI / "work-units").glob("*.yaml")}
    for wu_id, entry in (state.get("work_units") or {}).items():
        claims_done = entry.get("status") == "done"
        claims_accepted = entry.get("human_acceptance") == "accepted"
        if not claims_done and not claims_accepted:
            continue
        wu_path = wu_files.get(wu_id)
        wu_data = load_yaml(wu_path) if wu_path else None
        if wu_data is None:
            errors.append(
                f"project-state.yaml: {wu_id} marked done but work-units/{wu_id}.yaml is missing"
            )
            continue
        if claims_done and wu_data.get("status") != "done":
            errors.append(
                f"project-state.yaml claims {wu_id} is done, but work-units/{wu_id}.yaml "
                f"status is '{wu_data.get('status')}'"
            )
        if claims_accepted and (wu_data.get("outcomes") or {}).get("human_acceptance") != "accepted":
            errors.append(
                f"project-state.yaml claims {wu_id} human_acceptance is accepted, but "
                f"work-units/{wu_id}.yaml outcomes.human_acceptance disagrees"
            )
        done_event = entry.get("done_event")
        if done_event and not (AI / "events" / f"{done_event}.yaml").exists():
            errors.append(f"project-state.yaml: {wu_id}.done_event references missing event: {done_event}")
        acceptance_package = entry.get("acceptance_package")
        if acceptance_package and not (ROOT / acceptance_package).exists():
            errors.append(
                f"project-state.yaml: {wu_id}.acceptance_package references missing file: {acceptance_package}"
            )
        for ev_id in entry.get("evidence") or []:
            if not (AI / "evidence" / f"{ev_id}.yaml").exists():
                errors.append(f"project-state.yaml: {wu_id} references missing evidence: {ev_id}")

for p in sorted((AI / "events").glob("*.yaml")):
    validate_instance(p, "event.schema.json")
for p in sorted((AI / "evidence").glob("*.yaml")):
    validate_instance(p, "evidence.schema.json")
for p in sorted((AI / "findings").glob("*.yaml")):
    validate_instance(p, "finding.schema.json")
for p in sorted((AI / "observations").glob("*.yaml")):
    validate_instance(p, "observation.schema.json")
for p in sorted((AI / "retrospectives").glob("*.yaml")):
    validate_instance(p, "retrospective.schema.json")
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

# Retrospectives are derived snapshots. Their observation references must
# continue to resolve so an exported metric can always be traced back to its
# project-local source object.
observation_ids = {
    data.get("id")
    for path in (AI / "observations").glob("*.yaml")
    if (data := load_yaml(path)) and data.get("id")
}
for retrospective_path in sorted((AI / "retrospectives").glob("*.yaml")):
    retrospective = load_yaml(retrospective_path) or {}
    for observation_id in retrospective.get("observation_refs") or []:
        if observation_id not in observation_ids:
            errors.append(
                f"{retrospective_path.relative_to(ROOT)} references missing observation: "
                f"{observation_id}"
            )

print("Governed AI Team validation")
print("=" * 28)
for w in warnings:
    print(f"WARN  {w}")
for e in errors:
    print(f"ERROR {e}")
print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
sys.exit(1 if errors else 0)
