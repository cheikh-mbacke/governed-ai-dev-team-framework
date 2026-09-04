#!/usr/bin/env python3
"""Validate file ownership inventory against delivered scope (Document 11 §4)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID_OWNERS = frozenset({"core", "adapter:cursor", "distribution", "project"})

SCOPE_DIRS = (
    "tests/fixtures",
    ".fabric",
    "distribution/payload",
    ".cursor",
    "scripts",
    "tools",
    "adapters/cursor",
    "src",
)
SCOPE_FILES = ("AGENTS.md",)
EXCLUDE_DIR_NAMES = frozenset(
    {".git", "__pycache__", ".ruff_cache", ".pytest_cache", "node_modules"}
)

DEFAULT_INVENTORY = Path("tests/fixtures/legacy-0.4/file-ownership-inventory.json")


def normalize_path(path: str | Path) -> str:
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def classify_owner(path: str) -> str:
    """Map a delivered path to its unique owner (0.4.x classification rules)."""
    p = normalize_path(path)

    if p.startswith(".ai-team/runtime/governed_ai/adapters/cursor/"):
        return "adapter:cursor"
    if p.startswith(".ai-team/runtime/governed_ai/"):
        return "core"
    if p == ".ai-team/requirements.txt":
        return "core"
    if p.startswith(".cursor/"):
        return "adapter:cursor"
    if p == "tools/install.py":
        return "distribution"
    if p.startswith("tools/"):
        return "core"
    if p == ".ai-team/framework-version.json":
        return "distribution"
    if p == ".ai-team/installation-record.json":
        return "distribution"
    if p == "AGENTS.md":
        return "core"
    if p == "README.md":
        return "core"
    # Historical 0.4–0.6 installed paths only. Current framework-source docs
    # are source-only and never enter the installation ownership inventory.
    if p.startswith("docs/product/"):
        return "core"
    if p.startswith("docs/operator/"):
        return "core"
    if p.startswith("src/"):
        return "core"
    if p.startswith("adapters/cursor/"):
        return "adapter:cursor"
    if p.startswith("scripts/ai-team/"):
        return "core"
    if p.startswith("tests/fixtures/"):
        return "core"
    if p == ".fabric/framework-version.json":
        return "distribution"
    if p == ".fabric/project-profile.yaml":
        return "distribution"
    if p.startswith(".fabric/logs/"):
        return "core"
    if p.startswith("distribution/payload/.ai-team/constitution/"):
        return "core"
    if p.startswith("distribution/payload/.ai-team/contracts/"):
        return "core"
    if p.startswith("distribution/payload/.ai-team/schemas/"):
        return "core"
    if p.startswith("distribution/payload/.ai-team/templates/"):
        return "core"
    if p == "distribution/payload/.ai-team/migration-backups/.gitignore":
        return "core"
    if p.startswith("distribution/payload/seeds/"):
        return "distribution"
    if p.startswith(".ai-team/constitution/"):
        return "core"
    if p.startswith(".ai-team/contracts/"):
        return "core"
    if p.startswith(".ai-team/schemas/"):
        return "core"
    if p.startswith(".ai-team/templates/"):
        return "core"
    if p == ".ai-team/migration-backups/.gitignore":
        return "core"

    project_prefixes = (
        ".ai-team/project-profile.yaml",
        ".ai-team/sources/",
        ".ai-team/work-units/",
        ".ai-team/state/",
        ".ai-team/decisions/",
        ".ai-team/events/",
        ".ai-team/evidence/",
        ".ai-team/findings/",
        ".ai-team/audits/",
        ".ai-team/releases/",
        ".ai-team/acceptance/",
        ".ai-team/authorizations/",
        ".ai-team/context-packages/",
        ".ai-team/logs/",
        ".ai-team/metrics/",
        ".ai-team/observations/",
        ".ai-team/retrospectives/",
        ".ai-team/reconciliation/",
        ".ai-team/migration-backups/",
    )
    for prefix in project_prefixes:
        if p == prefix or p.startswith(prefix):
            return "project"

    raise ValueError(f"Unclassified path: {p}")


def should_skip(path: Path, root: Path | None = None) -> bool:
    if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
        return True
    if ".transactions" in path.parts:
        return True
    if root is not None:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            return False
        if rel.startswith("tests/fixtures/projects/"):
            return True
        if rel.startswith("src/governed_ai_dev_team_framework.egg-info/"):
            return True
        if rel.startswith(".ai-team/logs/") and rel.endswith(".jsonl"):
            return True
        if rel.startswith(".fabric/logs/") and rel.endswith(".jsonl"):
            return True
    return False


def iter_scope_files(root: Path) -> list[str]:
    files: list[str] = []
    for scope_dir in SCOPE_DIRS:
        base = root / scope_dir
        if not base.exists():
            continue
        if base.is_file():
            if not should_skip(base, root):
                files.append(normalize_path(base.relative_to(root)))
            continue
        for candidate in sorted(base.rglob("*")):
            if candidate.is_file() and not should_skip(candidate, root):
                files.append(normalize_path(candidate.relative_to(root)))
    for scope_file in SCOPE_FILES:
        candidate = root / scope_file
        if candidate.is_file():
            files.append(normalize_path(scope_file))
    return sorted(set(files))


def load_inventory(inventory_path: Path) -> dict:
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("files"), dict):
        raise TypeError("inventory must contain a 'files' mapping")
    return data


def validate_ownership(root: Path, inventory_path: Path) -> list[str]:
    errors: list[str] = []
    if not inventory_path.is_file():
        return [f"Missing inventory file: {inventory_path}"]

    scope_files = set(iter_scope_files(root))
    inventory = load_inventory(inventory_path)
    inv_map: dict[str, str] = inventory["files"]

    for path in sorted(scope_files - set(inv_map)):
        errors.append(f"Missing inventory entry for delivered file: {path}")

    for path in sorted(set(inv_map) - scope_files):
        errors.append(f"Orphan inventory entry (path not in scope): {path}")

    for path in sorted(scope_files & set(inv_map)):
        owner = inv_map[path]
        if owner not in VALID_OWNERS:
            errors.append(f"Invalid owner '{owner}' for {path}")
            continue
        try:
            expected = classify_owner(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if owner != expected:
            errors.append(
                f"Owner mismatch for {path}: inventory={owner}, expected={expected}"
            )

    return errors


def generate_inventory(root: Path) -> dict:
    files = iter_scope_files(root)
    return {
        "schema_version": 1,
        "framework_version": "0.7.0",
        "description": "File ownership inventory for delivered 0.4.x scope (Document 11 §4).",
        "owners": sorted(VALID_OWNERS),
        "scope_dirs": list(SCOPE_DIRS),
        "scope_files": list(SCOPE_FILES),
        "files": {path: classify_owner(path) for path in files},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="Path to ownership inventory JSON",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Write inventory JSON from classification rules and exit",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    inventory_path = (
        args.inventory if args.inventory.is_absolute() else root / args.inventory
    )

    profile_path = root / ".fabric" / "project-profile.yaml"
    if not profile_path.is_file():
        profile_path = root / ".ai-team" / "project-profile.yaml"
    if profile_path.is_file():
        for line in profile_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("repository_kind:"):
                kind = line.split(":", 1)[1].strip()
                if kind != "framework_source":
                    print(
                        f"Error: validate_ownership.py only applies to framework_source "
                        f"repositories (this project declares repository_kind: {kind!r}). "
                        f"Run validate.py instead.",
                        file=sys.stderr,
                    )
                    return 1
                break

    if args.generate:
        payload = generate_inventory(root)
        inventory_path.parent.mkdir(parents=True, exist_ok=True)
        inventory_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(payload['files'])} entries to {inventory_path}")
        return 0

    errors = validate_ownership(root, inventory_path)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"Ownership validation failed ({len(errors)} error(s)).", file=sys.stderr)
        return 1

    print(
        f"Ownership validation passed ({len(iter_scope_files(root))} files, "
        f"inventory {inventory_path.relative_to(root)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
