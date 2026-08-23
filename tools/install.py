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
profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
profile["project"]["id"] = args.project_id
profile["project"]["name"] = args.project_name
profile["project"]["repository_kind"] = "existing_or_greenfield_project"
profile["setup_status"]["template"] = False
profile["setup_status"]["note"] = "Complete commands, paths and human authorities before production use."
profile_path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")

state_path = target / ".ai-team" / "state" / "project-state.yaml"
state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
state["project_id"] = args.project_id
state_path.write_text(yaml.safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8")

product_docs = target / "docs" / "product"
product_docs.mkdir(parents=True, exist_ok=True)
readme = product_docs / "README.md"
if not readme.exists():
    readme.write_text("# Human product material\n\nPlace authoritative product documents here, then register them in `.ai-team/sources/source-registry.yaml`.\n", encoding="utf-8")

print(f"Installed governed AI team framework into {target}")
print("Next:")
print("  1. Fill .ai-team/project-profile.yaml")
print("  2. Add product documents under docs/product/")
print("  3. Register authoritative sources in .ai-team/sources/source-registry.yaml")
print("  4. Run: python scripts/ai-team/validate.py")
print("  5. In Cursor, invoke /compile-project")
