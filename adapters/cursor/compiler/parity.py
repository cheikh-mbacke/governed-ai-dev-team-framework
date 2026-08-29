"""Shadow and golden compile parity helpers (Document 13 Phase 4 §4.2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from adapters.cursor.compiler.compile import compile_manifest
from adapters.cursor.compiler.staging import sha256_bytes

DiffKind = Literal["missing_in_compile", "extra_in_compile", "content_mismatch"]

TEXT_SUFFIXES = {".md", ".mdc", ".json", ".txt", ".cmd", ".yaml", ".yml", ".py"}
AGENT_LINE_ENDING_NOTE = (
    "Compiled agent frontmatter uses LF line endings; historical .cursor/agents "
    "may retain CRLF on Windows until normalized on the next compile sync."
)


def normalize_text_bytes(data: bytes) -> bytes:
    """Normalize CRLF to LF for deterministic text comparison."""
    if b"\r" not in data:
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def normalize_for_compare(path: str, data: bytes) -> bytes:
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SUFFIXES or path.endswith(".cursor/.gitattributes"):
        return normalize_text_bytes(data)
    return data


def resolve_bundle_dir(source_root: Path) -> Path:
    """Prefer published bundle under .ai-team, fall back to dev bundle v1."""
    source_root = source_root.resolve()
    pointer = source_root / ".ai-team" / "contracts" / "active-bundle.json"
    if pointer.is_file():
        data = json.loads(pointer.read_text(encoding="utf-8"))
        rel = data.get("path")
        if isinstance(rel, str):
            candidate = (source_root / ".ai-team" / "contracts" / rel).resolve()
            if candidate.is_dir() and (candidate / "manifest.json").is_file():
                return candidate
    published = source_root / ".ai-team" / "contracts" / "bundles" / "1.0.0"
    if published.is_dir() and (published / "manifest.json").is_file():
        return published
    dev = source_root / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
    if dev.is_dir() and (dev / "manifest.json").is_file():
        return dev
    raise FileNotFoundError(f"no Published Contract Bundle found under {source_root}")


def _cursor_relative(path: Path, cursor_root: Path) -> str:
    rel = path.relative_to(cursor_root).as_posix()
    return f".cursor/{rel}"


def _collect_cursor_files(cursor_root: Path) -> dict[str, Path]:
    if not cursor_root.is_dir():
        return {}
    files: dict[str, Path] = {}
    for path in sorted(cursor_root.rglob("*")):
        if path.is_file():
            files[_cursor_relative(path, cursor_root)] = path
    return files


@dataclass(frozen=True)
class ShadowDiff:
    path: str
    kind: DiffKind
    explainable: bool
    reason: str | None = None


@dataclass
class ShadowReport:
    bundle_version: str
    historical_root: str
    diffs: list[ShadowDiff] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.diffs or all(item.explainable for item in self.diffs)

    def format(self) -> str:
        if not self.diffs:
            return "Shadow compile: no divergences from historical .cursor/."
        lines = [f"Shadow compile divergences ({len(self.diffs)}):", ""]
        for item in self.diffs:
            flag = "explainable" if item.explainable else "BLOCKING"
            lines.append(f"[{flag}] {item.kind} {item.path}")
            if item.reason:
                lines.append(f"  reason: {item.reason}")
        return "\n".join(lines)


def shadow_compare(
    bundle_dir: Path,
    historical_cursor_dir: Path,
    staging_dir: Path,
    project_profile: dict[str, Any] | None = None,
    *,
    templates_root: Path | None = None,
) -> ShadowReport:
    """Compile to staging without installing, compare to historical ``.cursor/``."""
    manifest = compile_manifest(
        bundle_dir,
        staging_dir,
        project_profile,
        templates_root=templates_root,
    )
    historical_cursor_dir = historical_cursor_dir.resolve()
    staged_cursor = staging_dir.resolve() / ".cursor"

    historical = _collect_cursor_files(historical_cursor_dir)
    compiled = _collect_cursor_files(staged_cursor)
    diffs: list[ShadowDiff] = []

    for rel in sorted(set(historical) - set(compiled)):
        diffs.append(
            ShadowDiff(
                path=rel,
                kind="missing_in_compile",
                explainable=False,
                reason="compiled tree omits historical artefact",
            )
        )

    for rel in sorted(set(compiled) - set(historical)):
        diffs.append(
            ShadowDiff(
                path=rel,
                kind="extra_in_compile",
                explainable=False,
                reason="compiled tree adds unexpected artefact",
            )
        )

    for rel in sorted(set(historical) & set(compiled)):
        hist_bytes = normalize_for_compare(rel, historical[rel].read_bytes())
        comp_bytes = normalize_for_compare(rel, compiled[rel].read_bytes())
        if hist_bytes == comp_bytes:
            continue
        explainable = False
        reason = "content mismatch"
        if rel.startswith(".cursor/agents/") and rel.endswith(".md"):
            raw_hist = historical[rel].read_bytes()
            raw_comp = compiled[rel].read_bytes()
            if normalize_text_bytes(raw_hist) == normalize_text_bytes(raw_comp):
                explainable = True
                reason = AGENT_LINE_ENDING_NOTE
            elif hist_bytes != comp_bytes:
                reason = "agent frontmatter/body differs after normalization"
        diffs.append(
            ShadowDiff(
                path=rel,
                kind="content_mismatch",
                explainable=explainable,
                reason=reason,
            )
        )

    return ShadowReport(
        bundle_version=str(manifest["bundle_version"]),
        historical_root=str(historical_cursor_dir),
        diffs=diffs,
    )


@dataclass(frozen=True)
class GoldenManifest:
    schema_version: int
    bundle_version: str
    adapter_version: str
    documented_differences: list[dict[str, Any]]
    artifacts: list[dict[str, str]]

    @classmethod
    def load(cls, path: Path) -> GoldenManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(data["schema_version"]),
            bundle_version=str(data["bundle_version"]),
            adapter_version=str(data["adapter_version"]),
            documented_differences=list(data.get("documented_differences") or []),
            artifacts=list(data["artifacts"]),
        )

    def artifact_map(self) -> dict[str, str]:
        return {entry["path"]: entry["sha256"] for entry in self.artifacts}


def build_golden_manifest(
    compile_manifest_payload: dict[str, Any],
    *,
    documented_differences: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "bundle_version": compile_manifest_payload["bundle_version"],
        "adapter_version": compile_manifest_payload["adapter_version"],
        "documented_differences": documented_differences
        or [
            {
                "kind": "line_endings",
                "paths": [".cursor/agents/*.md"],
                "explanation": AGENT_LINE_ENDING_NOTE,
            }
        ],
        "artifacts": compile_manifest_payload["artifacts"],
    }


def verify_golden_compile(
    staging_dir: Path,
    golden: GoldenManifest,
) -> list[str]:
    """Return human-readable mismatches against a frozen golden manifest."""
    errors: list[str] = []
    staging_dir = staging_dir.resolve()
    expected = golden.artifact_map()

    for rel, digest in sorted(expected.items()):
        target = staging_dir / rel
        if not target.is_file():
            errors.append(f"missing staged artefact: {rel}")
            continue
        actual = sha256_bytes(target.read_bytes())
        if actual != digest:
            errors.append(f"hash mismatch for {rel}: expected {digest}, got {actual}")

    staged_paths = {
        f".cursor/{path.relative_to(staging_dir / '.cursor').as_posix()}"
        for path in (staging_dir / ".cursor").rglob("*")
        if path.is_file()
    }
    for rel in sorted(staged_paths - set(expected)):
        errors.append(f"unexpected staged artefact not in golden: {rel}")
    return errors


__all__ = [
    "GoldenManifest",
    "ShadowDiff",
    "ShadowReport",
    "build_golden_manifest",
    "normalize_for_compare",
    "resolve_bundle_dir",
    "shadow_compare",
    "verify_golden_compile",
]
