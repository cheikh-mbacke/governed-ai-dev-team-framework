"""Instance-only install policy (Document 25 INS-ADR-008 / INS-F-002 / INS-F-014).

Standalone in-tree installs are no longer a supported product mode. Fresh install
targets must be dedicated instance directories; existing standalone trees must use
``tools/migrate_to_instance.py``.
"""

from __future__ import annotations

from pathlib import Path

from distribution.installer.record import INSTALLATION_RECORD_FILE

# Heuristic roots that usually mean "existing product code" (aligned with assessment).
_APPLICATION_ROOT_CANDIDATES = (
    "src",
    "app",
    "lib",
    "libs",
    "packages",
    "backend",
    "frontend",
    "server",
    "client",
    "cmd",
    "internal",
    "pkg",
)

_APPLICATION_FILE_CANDIDATES = (
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
)

MIGRATE_HINT = (
    "Standalone in-tree installs are no longer supported. "
    "Create a dedicated instance directory and register product Git checkouts as "
    "members, or migrate an existing 0.7.x install with:\n"
    "  python tools/migrate_to_instance.py \\\n"
    "    --source <product-repo> \\\n"
    "    --instance <empty-instance-dir> \\\n"
    "    --ensemble-id <id> \\\n"
    "    --member-id <id>"
)


def list_application_markers(target: Path) -> list[str]:
    """Return relative paths that indicate product application code at ``target``."""
    markers: list[str] = []
    for name in _APPLICATION_ROOT_CANDIDATES:
        path = target / name
        if path.is_dir() and any(path.iterdir()):
            markers.append(f"{name}/")
    for name in _APPLICATION_FILE_CANDIDATES:
        if (target / name).is_file():
            markers.append(name)
    for path in sorted(target.glob("*.py")):
        markers.append(path.name)
    docs_product = target / "docs" / "product"
    if docs_product.is_dir() and any(docs_product.rglob("*")):
        markers.append("docs/product/")
    return markers


def fresh_install_product_code_error(target: Path) -> str | None:
    """Refuse fresh install when the target looks like a product checkout."""
    markers = list_application_markers(target)
    if not markers:
        return None
    shown = ", ".join(markers[:8])
    more = "" if len(markers) <= 8 else f" (+{len(markers) - 8} more)"
    return (
        "Fresh install refused: target contains application/product markers "
        f"({shown}{more}).\n"
        f"{MIGRATE_HINT}"
    )


def _catalog_has_out_of_tree_members(target: Path) -> bool:
    catalog_path = target / ".ai-team" / "catalog.yaml"
    if not catalog_path.is_file():
        return False
    try:
        import yaml
    except ModuleNotFoundError:
        return False
    try:
        document = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(document, dict):
        return False
    ensembles = document.get("ensembles")
    if not isinstance(ensembles, list) or not ensembles:
        return False
    ensembles_root = target / ".ai-team" / "ensembles"
    for entry in ensembles:
        if not isinstance(entry, dict):
            continue
        ensemble_id = entry.get("id")
        if not isinstance(ensemble_id, str) or not ensemble_id:
            continue
        members_path = ensembles_root / ensemble_id / "members.yaml"
        if not members_path.is_file():
            continue
        try:
            members_doc = yaml.safe_load(members_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(members_doc, dict):
            continue
        for member in members_doc.get("members") or []:
            if not isinstance(member, dict):
                continue
            raw = member.get("path")
            if not isinstance(raw, str) or not raw.strip():
                continue
            resolved = (target / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
            try:
                if resolved.resolve() != target.resolve():
                    return True
            except OSError:
                return True
    return False


def is_standalone_in_tree_install(target: Path) -> bool:
    """True when target has a framework install that still lives in a product tree."""
    if not (target / INSTALLATION_RECORD_FILE).is_file():
        return False
    if _catalog_has_out_of_tree_members(target):
        return False
    # Empty dedicated instance: no application markers → not standalone.
    if not list_application_markers(target):
        return False
    return True


def update_standalone_refused_error(target: Path) -> str | None:
    """Refuse ``--update`` on a standalone in-tree install."""
    if not is_standalone_in_tree_install(target):
        return None
    return (
        "Update refused: target is a standalone in-tree install, which is no longer "
        "supported.\n"
        f"{MIGRATE_HINT}"
    )
