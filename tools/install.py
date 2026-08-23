#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import yaml

parser = argparse.ArgumentParser(description="Install Governed AI Dev Team framework into an existing repository")
parser.add_argument("--target", required=True)
parser.add_argument("--project-id", required=True)
parser.add_argument("--project-name", required=True)
parser.add_argument("--force", action="store_true")
args = parser.parse_args()

source_root = Path(__file__).resolve().parents[1]
target = Path(args.target).expanduser().resolve()
target.mkdir(parents=True, exist_ok=True)

copy_items = [".cursor", ".ai-team", "scripts", "AGENTS.md"]
for item in copy_items:
    src = source_root / item
    dst = target / item
    if src.is_dir():
        if dst.exists() and not args.force:
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
        if not dst.exists() or args.force:
            shutil.copy2(src, dst)

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
    print("NOTE: project-profile.yaml did not match the shipped template exactly; "
          "rewrote it structurally (comments, if any, were not preserved).")

state_path = target / ".ai-team" / "state" / "project-state.yaml"
state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
state["project_id"] = args.project_id
state_path.write_text(yaml.safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8")

product_docs = target / "docs" / "product"
product_docs.mkdir(parents=True, exist_ok=True)
readme = product_docs / "README.md"
if not readme.exists():
    readme.write_text(
        "# Human product material\n\n"
        "Put your authoritative product documents under the subfolders below "
        "(or register files from their actual location in "
        "`.ai-team/sources/source-registry.yaml` — nothing has to physically "
        "live here). The subfolders are an optional organizational aid, not a "
        "required format: use as many or as few as your project needs, and "
        "put more than one topic in a single file if that's simpler for you. "
        "They mirror the construction-material checklist in the framework's "
        "base design document (see `docs/SOURCE_MAPPING.md`).\n\n"
        "- `vision-and-scope/` — what result you're after, and what's explicitly out of scope.\n"
        "- `users-and-rules/` — who uses the system, their journeys, and the business rules/invariants that govern behavior.\n"
        "- `requirements/` — functional and non-functional requirements, and any specification detail needed to avoid ambiguity.\n"
        "- `acceptance-criteria/` — the observable results that make a piece of work count as done.\n"
        "- `architecture-and-constraints/` — architecture, interface contracts, and imposed technical constraints (stack, versions, environments).\n"
        "- `security-and-compliance/` — access control, data, secrets, audit and regulatory requirements.\n"
        "- `references/` — reference data, examples, mockups or expected proof artifacts.\n",
        encoding="utf-8",
    )

product_doc_subfolders = {
    "vision-and-scope": "Vision and measurable objectives; what's included and explicitly excluded.",
    "users-and-rules": "Actors, user journeys; business rules, invariants, decisions and exceptions.",
    "requirements": "Functional and non-functional requirements; specification detail that removes ambiguity.",
    "acceptance-criteria": "Observable results that let you consider a piece of work done.",
    "architecture-and-constraints": "Architecture, interface contracts; imposed technologies, versions, environments.",
    "security-and-compliance": "Access control, data, secrets, audit and regulatory requirements.",
    "references": "Reference data, examples, mockups, or proof artifacts that reduce ambiguity.",
}
for folder_name, prompt in product_doc_subfolders.items():
    folder_path = product_docs / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    stub = folder_path / "README.md"
    if not stub.exists():
        stub.write_text(f"# {folder_name.replace('-', ' ').title()}\n\n{prompt}\n", encoding="utf-8")

print(f"Installed governed AI team framework into {target}")
print("Next:")
print("  1. Fill .ai-team/project-profile.yaml (or ask Cursor: /propose-profile)")
print("  2. Add product documents under docs/product/<category>/")
print("  3. Register authoritative sources in .ai-team/sources/source-registry.yaml (or ask Cursor: /propose-profile)")
print("  4. Run: python scripts/ai-team/validate.py")
print("  5. In Cursor, invoke /compile-project")
