#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import sys
import fnmatch

try:
    import yaml
except ModuleNotFoundError:
    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

parser = argparse.ArgumentParser(description="Install Governed AI Dev Team framework into an existing repository")
parser.add_argument("--target", required=True)
parser.add_argument("--project-id", required=True)
parser.add_argument("--project-name", required=True)
parser.add_argument("--force", action="store_true")
parser.add_argument("--update", action="store_true",
    help="Overwrite framework/governance files (agents, skills, rules, hooks, UI and CLI "
         "permissions, "
         "constitution, schemas, scripts) with the latest version from this clone, without "
         "touching project data (project-profile.yaml, source-registry.yaml, Work Units, "
         "state, decisions, events, evidence, findings, audits, releases, acceptance, logs, "
         "or any product document you've written under docs/product/). Use this to pick up "
         "framework fixes on a project you already installed into.")
args = parser.parse_args()

if args.update and args.force:
    print("--update and --force are mutually exclusive: --force overwrites everything "
          "including your project data, --update is specifically designed not to. Pick one.")
    raise SystemExit(2)

target = Path(args.target).expanduser().resolve()

if args.update and not (target / ".ai-team" / "project-profile.yaml").exists():
    print(f"--update expects an already-installed project at {target}, but "
          "no .ai-team/project-profile.yaml was found there. Run a normal install "
          "first (no --update), then use --update for subsequent framework updates.")
    raise SystemExit(2)

source_root = Path(__file__).resolve().parents[1]
target.mkdir(parents=True, exist_ok=True)

# Paths (relative to the project root) that belong to YOUR project, never the
# framework - --update must never overwrite these even though they live
# under directories (.ai-team/, docs/product/) that otherwise get refreshed.
# Patterns are matched with fnmatch against the path relative to target.
PROJECT_OWNED_PATTERNS = [
    ".ai-team/project-profile.yaml",
    ".ai-team/sources/source-registry.yaml",
    ".ai-team/work-units/*",
    ".ai-team/state/*",
    ".ai-team/decisions/*",
    ".ai-team/events/*",
    ".ai-team/evidence/*",
    ".ai-team/findings/*",
    ".ai-team/audits/*",
    ".ai-team/releases/*",
    ".ai-team/acceptance/*",
    ".ai-team/context-packages/*",
    ".ai-team/logs/*",
    ".ai-team/project-profile.yaml.bak",
]


def is_project_owned(rel_posix):
    for pattern in PROJECT_OWNED_PATTERNS:
        if fnmatch.fnmatch(rel_posix, pattern):
            return True
    return False


def is_docs_product_readme(rel_posix):
    # docs/product/README.md and docs/product/<category>/README.md are
    # framework-authored stubs (safe to refresh). Any other file under
    # docs/product/ is the human's own product material - never touched
    # by --update, even though it lives in a directory that otherwise gets
    # refreshed.
    return rel_posix == "docs/product/README.md" or (
        rel_posix.startswith("docs/product/") and rel_posix.endswith("/README.md")
        and rel_posix.count("/") == 3
    )


copy_items = [".cursor", ".ai-team", "scripts", "docs/product", "AGENTS.md", "requirements.txt"]
updated_files = []
skipped_project_data = []
for item in copy_items:
    src = source_root / item
    dst = target / item
    if src.is_dir():
        if args.update and dst.exists():
            for p in src.rglob("*"):
                if p.is_dir():
                    continue
                rel = p.relative_to(source_root)
                rel_posix = rel.as_posix()
                out = target / rel
                if item == "docs/product" and not is_docs_product_readme(rel_posix):
                    continue  # human's own product material - never touched
                if is_project_owned(rel_posix):
                    if out.exists():
                        skipped_project_data.append(rel_posix)
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out)
                updated_files.append(rel_posix)
        elif dst.exists() and not args.force:
            # Merge without overwriting existing files.
            for p in src.rglob("*"):
                rel = p.relative_to(src)
                out = dst / rel
                if p.is_dir():
                    out.mkdir(parents=True, exist_ok=True)
                elif not out.exists():
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, out)
        else:
            shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        if args.update or not dst.exists() or args.force:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if args.update:
                updated_files.append(item)

if args.update:
    print(f"Updated {len(updated_files)} framework file(s) in {target} to the latest version.")
    print("Project data left untouched (project-profile.yaml, source-registry.yaml, Work Units,")
    print("state, decisions, events, evidence, findings, audits, releases, acceptance, logs,")
    print("and every file you've written under docs/product/ other than the category READMEs).")
    if skipped_project_data:
        print(f"({len(skipped_project_data)} project-data path(s) correctly left alone.)")
    print("\nRun python scripts/ai-team/validate.py to confirm nothing broke.")
    print("Before Cursor CLI, run python scripts/ai-team/preflight.py.")
    raise SystemExit(0)

profile_path = target / ".ai-team" / "project-profile.yaml"
profile_text = profile_path.read_text(encoding="utf-8")

# Rewrite specific known lines in place with plain text substitution rather
# than a full yaml.safe_load/safe_dump round trip: PyYAML's dumper silently
# drops all comments, which would strip the guidance example shipped at the
# top of this file. Each substitution is applied only if the exact shipped
# default line is still present and unique, so a hand-edited file is never
# corrupted by a partial or ambiguous match.
substitutions = [
    ("  id: framework-template", f"  id: {args.project_id}"),
    ("  name: Governed AI Development Team Framework", f"  name: {args.project_name}"),
    ("  repository_kind: framework_template", "  repository_kind: existing_or_greenfield_project"),
    ("  template: true", "  template: false"),
    (
        '  note: "The installer rewrites project.id, project.name and template=false. '
        'Fill repository-specific commands, paths and human authorities before production use."',
        '  note: "Complete commands, paths and human authorities before production use."',
    ),
]

if all(profile_text.count(old) == 1 for old, _ in substitutions):
    for old, new in substitutions:
        profile_text = profile_text.replace(old, new, 1)
    profile_path.write_text(profile_text, encoding="utf-8")
else:
    # Fallback for a project-profile.yaml that no longer matches the shipped
    # defaults exactly (e.g. re-running install against an already-edited
    # file): fall back to a structural rewrite. This still updates the
    # required fields correctly, but any comments in the file are lost.
    profile = yaml.safe_load(profile_text)
    profile["project"]["id"] = args.project_id
    profile["project"]["name"] = args.project_name
    profile["project"]["repository_kind"] = "existing_or_greenfield_project"
    profile["setup_status"]["template"] = False
    profile["setup_status"]["note"] = "Complete commands, paths and human authorities before production use."
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print("NOTE: .ai-team/project-profile.yaml already existed and didn't match "
          "the shipped template exactly (common if you're re-running install.py "
          "against a target you already installed into, or already edited by "
          "hand). project.id, project.name and setup_status were still updated "
          "correctly; only the commented example at the top of the file, if it "
          "was still there, was not preserved. Nothing to fix unless you want "
          "that comment back, in which case remove the target and reinstall "
          "into a fresh directory.")

state_path = target / ".ai-team" / "state" / "project-state.yaml"
state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
state["project_id"] = args.project_id
state_path.write_text(yaml.safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8")

print(f"Installed governed AI team framework into {target}")
print("Next:")
print("  1. Fill .ai-team/project-profile.yaml (or ask Cursor UI/CLI: /propose-profile)")
print("  2. Add product documents under docs/product/<category>/")
print(
    "  3. Register authoritative sources in .ai-team/sources/source-registry.yaml "
    "(or ask Cursor UI/CLI: /propose-profile)"
)
print("  4. Run: python scripts/ai-team/validate.py")
print("  5. Before Cursor CLI, run: python scripts/ai-team/preflight.py")
print("  6. In Cursor UI or interactive CLI, invoke /compile-project")
