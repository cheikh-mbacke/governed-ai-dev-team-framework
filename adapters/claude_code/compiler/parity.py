"""Golden compile parity helpers (mirrors adapters/cursor/compiler/parity.py).

Only the frozen-golden-manifest mechanism is ported here, not Cursor's
``shadow_compare`` (which diffs a fresh compile against a historical,
separately-checked-out ``.cursor/`` tree — no equivalent historical
``.claude/`` tree exists in this repo to compare against). Golden-manifest
verification alone — comparing a fresh compile to a frozen, reviewed hash
snapshot — is what "frozen golden fixtures" means for this Adaptateur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governed_ai.adapters.common.staging import sha256_bytes

__all__ = [
    "GoldenManifest",
    "build_golden_manifest",
    "verify_golden_compile",
]

CMD_LINE_ENDING_NOTE = (
    "Compiled text artefacts, including .claude/hooks/run_hook.cmd, are stored "
    "with LF line endings. Root .gitattributes maps *.cmd to CRLF in the "
    "working tree; the compiler normalizes before hash and write."
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
                "paths": [".claude/hooks/run_hook.cmd"],
                "explanation": CMD_LINE_ENDING_NOTE,
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

    claude_root = staging_dir / ".claude"
    staged_paths = {
        f".claude/{path.relative_to(claude_root).as_posix()}"
        for path in claude_root.rglob("*")
        if path.is_file()
    }
    for rel in sorted(staged_paths - set(expected)):
        errors.append(f"unexpected staged artefact not in golden: {rel}")
    return errors
