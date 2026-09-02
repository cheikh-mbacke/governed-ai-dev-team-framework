#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    from install_paths import requirements_install_hint

    print(
        "Missing dependency: PyYAML and/or jsonschema. "
        "Install them first, then re-run this command:"
    )
    print(f"  {requirements_install_hint(_ROOT)}")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

from i18n import project_language, t
from install_paths import bootstrap_runtime

bootstrap_runtime(_ROOT)

from governed_ai.core.fabrication_overlay import (
    collect_framework_source_fabrication_overlay_violations,
)
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import (
    collect_framework_source_client_cycle_artifacts,
    collect_framework_source_feedback_artifacts,
    collect_framework_source_root_layout_violations,
)

ROOT = _ROOT
WORKSPACE = Workspace.from_root(ROOT)
FABRIC = ROOT / ".fabric"
AI = WORKSPACE.ai_team
PROFILE_PATH = WORKSPACE.profile_path
IS_FABRICATION = (FABRIC / "project-profile.yaml").is_file()
VERSION_PATH = (
    FABRIC / "framework-version.json"
    if IS_FABRICATION
    else AI / "framework-version.json"
)
SEEDS = ROOT / "distribution" / "payload" / "seeds"
LANG = project_language(ROOT)

errors = []
warnings = []

if IS_FABRICATION:
    required = [
        FABRIC / "project-profile.yaml",
        FABRIC / "framework-version.json",
        AI / "constitution" / "constitution.yaml",
        SEEDS / "source-registry.yaml",
        SEEDS / "project-state.yaml",
        SEEDS / "project-profile.yaml",
        ROOT / ".cursor" / "hooks.json",
        ROOT / ".cursor" / "hooks" / "run_hook.cmd",
        ROOT / ".cursor" / "permissions.json",
        ROOT / ".cursor" / "cli.json",
        ROOT / "scripts" / "ai-team" / "migrate.py",
        ROOT / "scripts" / "ai-team" / "feedback.py",
        AI / "schemas" / "observation.schema.json",
        AI / "schemas" / "retrospective.schema.json",
        AI / "schemas" / "feedback-export.schema.json",
    ]
else:
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

version_path = VERSION_PATH
version_manifest = None
if version_path.exists():
    version_manifest = load_json(version_path)
    if version_manifest is not None:
        version_label = version_path.relative_to(ROOT).as_posix()
        if not isinstance(version_manifest.get("version"), str):
            errors.append(f"{version_label}: version must be a string")
        managed_files = version_manifest.get("managed_files")
        if managed_files is not None and (
            not isinstance(managed_files, list)
            or not all(isinstance(path, str) for path in managed_files)
        ):
            errors.append(f"{version_label}: managed_files must be a list of strings")

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

if PROFILE_PATH.is_file():
    profile = load_yaml(PROFILE_PATH) or {}
    if profile.get("setup_status", {}).get("template"):
        warnings.append("project-profile.yaml is still marked as template=true")
    for field in ["build", "lint", "unit_test"]:
        if profile.get("commands", {}).get(field) is None:
            warnings.append(f"Project command '{field}' is not configured")
    auth = profile.get("human_authorities", {})
    for k, v in auth.items():
        if v in (None, "unspecified", ""):
            warnings.append(f"Human authority '{k}' is unspecified")

    repository_kind = (profile.get("project") or {}).get("repository_kind")
    if repository_kind == "framework_source":
        errors.extend(collect_framework_source_root_layout_violations(ROOT))
        if (ROOT / ".ai-team" / "installation-record.json").exists():
            errors.append(
                "framework_source repository must not contain "
                ".ai-team/installation-record.json (installed targets only)"
            )
        if (ROOT / ".ai-team" / "runtime" / "governed_ai").is_dir():
            errors.append(
                "framework_source repository must not contain "
                ".ai-team/runtime/governed_ai/ (installed-target layout only)"
            )
        seed_state_path = SEEDS / "project-state.yaml"
        state_for_checks = load_yaml(seed_state_path) if seed_state_path.exists() else {}
        errors.extend(collect_framework_source_feedback_artifacts(AI))
        errors.extend(
            collect_framework_source_client_cycle_artifacts(AI, state=state_for_checks)
        )
        errors.extend(collect_framework_source_fabrication_overlay_violations(ROOT))
        if isinstance(version_manifest, dict):
            version_label = version_path.relative_to(ROOT).as_posix()
            for path in version_manifest.get("managed_files") or []:
                if not isinstance(path, str):
                    continue
                if path.startswith(".ai-team/runtime/"):
                    errors.append(
                        f"{version_label} lists installed-target path "
                        f"{path!r}; run scripts/ai-team/sync_source_manifest.py"
                    )
                elif not (ROOT / path).is_file():
                    errors.append(f"{version_label} lists missing source file: {path}")
            product_version = version_manifest.get("version")
            pyproject_path = ROOT / "pyproject.toml"
            if isinstance(product_version, str) and pyproject_path.is_file():
                import re

                pyproject_text = pyproject_path.read_text(encoding="utf-8")
                match = re.search(
                    r'(?m)^version\s*=\s*["\']([^"\']+)["\']\s*$',
                    pyproject_text,
                )
                pyproject_version = match.group(1) if match else None
                if pyproject_version and product_version != pyproject_version:
                    errors.append(
                        "product version mismatch: "
                        f"framework-version.json={product_version}, "
                        f"pyproject.toml={pyproject_version}"
                    )
            adapter_manifest_path = ROOT / "adapters" / "cursor" / "manifest.json"
            if isinstance(product_version, str) and adapter_manifest_path.is_file():
                if str(ROOT) not in sys.path:
                    sys.path.insert(0, str(ROOT))
                descriptor = load_json(adapter_manifest_path)
                if isinstance(descriptor, dict):
                    from distribution.installer.version_policy import (
                        validate_adapter_descriptor_alignment,
                    )

                    errors.extend(
                        validate_adapter_descriptor_alignment(
                            product_version,
                            "cursor",
                            descriptor,
                        )
                    )
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            src_root = ROOT / "src"
            if src_root.is_dir() and str(src_root) not in sys.path:
                sys.path.insert(0, str(src_root))
            from distribution.installer.version_policy import validate_release_matrix

            errors.extend(validate_release_matrix(ROOT))
    elif repository_kind == "existing_or_greenfield_project":
        if not (AI / "installation-record.json").is_file():
            warnings.append(
                "installed project profile without .ai-team/installation-record.json "
                "(expected after tools/install.py)"
            )

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

source_registry_path = None if IS_FABRICATION else AI / "sources" / "source-registry.yaml"
if source_registry_path is not None and source_registry_path.exists():
    reg = load_yaml(source_registry_path) or {}
    if not reg.get("sources"):
        warnings.append("No authoritative product sources are registered")

schema_dir = AI / "schemas"
legacy_counts = {}


def is_legacy_instance(data, schema_name):
    """Recognize immutable pre-revision artifacts without rewriting them.

    The early 0.4/0.5 governance records predate the mutable-v2 metadata
    (revision/created_at/updated_at) and the normalized evidence result object.
    They remain audit evidence and are therefore validated through a bounded
    compatibility profile instead of being migrated in place.
    """
    if not isinstance(data, dict):
        return False
    if schema_name in {"work-unit.schema.json", "decision.schema.json"}:
        return not {"revision", "created_at", "updated_at"}.issubset(data)
    if schema_name == "evidence.schema.json":
        return not isinstance(data.get("result"), dict)
    if schema_name == "event.schema.json":
        return data.get("type") not in {
            "STATUS",
            "CONTEXT_REQUEST",
            "CLARIFICATION_REQUEST",
            "DECISION_REQUEST",
            "BLOCKER",
            "CONTRACT_CHANGE",
            "REVIEW_REQUEST",
            "DEFECT",
            "SKILL_REQUEST",
            "HANDOFF",
        }
    return False


def validate_legacy_instance(data, instance_path, schema_name):
    required_by_schema = {
        "work-unit.schema.json": [
            "id", "title", "objective", "scope", "expected_behavior",
            "acceptance_criteria", "dependencies", "risk",
            "required_verification", "status",
        ],
        "decision.schema.json": [
            "id", "question", "why_human_authority_is_required", "options", "status",
        ],
        "evidence.schema.json": ["id", "type", "result"],
        "event.schema.json": ["id", "type", "summary", "status"],
    }
    missing = [field for field in required_by_schema[schema_name] if field not in data]
    if missing:
        errors.append(
            f"{instance_path.relative_to(ROOT)}: legacy compatibility profile is missing "
            + ", ".join(missing)
        )
    if not isinstance(data.get("id"), str) or not data.get("id"):
        errors.append(f"{instance_path.relative_to(ROOT)}: legacy id must be a non-empty string")
    legacy_counts[schema_name] = legacy_counts.get(schema_name, 0) + 1

def validate_instance(instance_path, schema_name):
    data = load_yaml(instance_path)
    if data is None:
        return
    if is_legacy_instance(data, schema_name):
        validate_legacy_instance(data, instance_path, schema_name)
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
if IS_FABRICATION and (SEEDS / "source-registry.yaml").exists():
    validate_instance(SEEDS / "source-registry.yaml", "source-registry.schema.json")

state_path = AI / "state" / "project-state.yaml"
if state_path.exists():
    validate_instance(state_path, "project-state.schema.json")
    state_for_version = load_yaml(state_path) or {}
    constitution_for_version = load_yaml(AI / "constitution" / "constitution.yaml") or {}
    state_constitution_version = state_for_version.get("constitution_version")
    active_constitution_version = constitution_for_version.get("constitution", {}).get(
        "version"
    )
    if state_constitution_version != active_constitution_version:
        errors.append(
            "project-state.yaml constitution_version "
            f"{state_constitution_version!r} does not match active Constitution "
            f"{active_constitution_version!r}"
        )

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

for schema_name, count in sorted(legacy_counts.items()):
    warnings.append(
        f"{count} immutable legacy artifact(s) validated with the bounded "
        f"compatibility profile for {schema_name}"
    )

print(t(LANG, "Governed AI Team validation", "Validation Governed AI Team"))
print("=" * 28)
# Error/warning bodies below are left in English even in a French project:
# most embed file paths, YAML/JSON keys, or messages produced by PyYAML/
# jsonschema themselves, which are never translated - translating only the
# surrounding sentence would make these harder to read, not easier.
for w in warnings:
    print(f"WARN  {w}")
for e in errors:
    print(f"ERROR {e}")
print("\n" + t(LANG, f"{len(errors)} error(s), {len(warnings)} warning(s)", f"{len(errors)} erreur(s), {len(warnings)} avertissement(s)"))
sys.exit(1 if errors else 0)
