"""Source-to-destination path mapping for installed projects (Document 11 §4)."""

from __future__ import annotations

from pathlib import Path

from distribution.installer.record import normalize_path

# Direct copy: same relative path in framework source and target project.
DIRECT_COPY_ITEMS = (
    ".ai-team",
    "scripts",
    "AGENTS.md",
)

# Relocated items: framework-source prefix -> target-project prefix.
RELOCATED_COPY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("src/governed_ai", ".ai-team/runtime/governed_ai"),
    ("adapters/cursor", ".ai-team/runtime/governed_ai/adapters/cursor"),
)

RELOCATED_COPY_FILES: tuple[tuple[str, str], ...] = (
    ("requirements.txt", ".ai-team/requirements.txt"),
)

RUNTIME_GOVERNED_AI = Path(".ai-team/runtime/governed_ai")
RUNTIME_REQUIREMENTS = Path(".ai-team/requirements.txt")

# Legacy layout paths (v0.6.x) superseded by RELOCATED_COPY_* above.
LEGACY_RELOCATED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("src/governed_ai", ".ai-team/runtime/governed_ai"),
    ("adapters/cursor", ".ai-team/runtime/governed_ai/adapters/cursor"),
)

LEGACY_ROOT_MANAGED_FILES = frozenset(
    {
        "README.md",
        "requirements.txt",
    }
)

LEGACY_AMBIGUOUS_ROOT_FILES = frozenset({"README.md", "requirements.txt", "AGENTS.md"})

FORENSIC_REVIEW_PATHS = LEGACY_AMBIGUOUS_ROOT_FILES


def map_source_relative_to_target(source_rel: str) -> str:
    """Map a framework-source relative path to the installed target path."""
    rel = normalize_path(source_rel)
    for src_prefix, dest_prefix in RELOCATED_COPY_PREFIXES:
        if rel == src_prefix or rel.startswith(src_prefix + "/"):
            suffix = rel[len(src_prefix) :].lstrip("/")
            return f"{dest_prefix}/{suffix}" if suffix else dest_prefix
    for src_file, dest_file in RELOCATED_COPY_FILES:
        if rel == src_file:
            return dest_file
    return rel


def map_target_relative_to_source(target_rel: str) -> str | None:
    """Reverse map an installed target path to framework source, if relocated."""
    rel = normalize_path(target_rel)
    # Longest dest prefix first so nested relocations (e.g. adapters/cursor) win
    # over the parent runtime/governed_ai prefix.
    for src_prefix, dest_prefix in sorted(
        RELOCATED_COPY_PREFIXES, key=lambda pair: len(pair[1]), reverse=True
    ):
        if rel == dest_prefix or rel.startswith(dest_prefix + "/"):
            suffix = rel[len(dest_prefix) :].lstrip("/")
            return f"{src_prefix}/{suffix}" if suffix else src_prefix
    for src_file, dest_file in RELOCATED_COPY_FILES:
        if rel == dest_file:
            return src_file
    return None


def is_installed_runtime_layout(target: Path) -> bool:
    return (target / RUNTIME_GOVERNED_AI).is_dir()


def runtime_sys_path_entry(target: Path) -> Path | None:
    """Directory to prepend to sys.path for ``import governed_ai`` in a target project."""
    runtime_parent = target / ".ai-team" / "runtime"
    if (runtime_parent / "governed_ai").is_dir():
        return runtime_parent
    legacy_src = target / "src"
    if (legacy_src / "governed_ai").is_dir():
        return legacy_src
    return None


def compile_source_root(source_root: Path, target: Path | None = None) -> Path:
    """Root passed to the Cursor compiler: framework repo or installed target."""
    if target is not None and is_installed_runtime_layout(target):
        return target.resolve()
    return source_root.resolve()


def adapter_templates_root(source_root: Path, target: Path | None = None) -> Path:
    root = compile_source_root(source_root, target)
    installed = root / ".ai-team" / "runtime" / "governed_ai" / "adapters" / "cursor" / "templates"
    if installed.is_dir():
        return installed
    return root / "adapters" / "cursor" / "templates"


def adapter_compiler_import_root(source_root: Path, target: Path | None = None) -> Path:
    """Root whose ``src`` or ``runtime`` entry enables governed_ai imports for compile."""
    root = compile_source_root(source_root, target)
    if is_installed_runtime_layout(root):
        return root / ".ai-team" / "runtime"
    return root
