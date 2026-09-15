"""Bundle directory resolution shared by every Adaptateur (Document 12 §3.2).

Extracted from ``adapters/cursor/compiler/parity.py`` — no Cursor-specific
content: it only knows about the Published Contract Bundle's own
conventional locations (``.ai-team/contracts/...``, dev bundle under
``src/governed_ai/contracts/bundles/v1``).
"""

from __future__ import annotations

import json
from pathlib import Path


def resolve_bundle_dir(source_root: Path, *, target: Path | None = None) -> Path:
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
    runtime_dev = (
        source_root / ".ai-team" / "runtime" / "governed_ai" / "contracts" / "bundles" / "v1"
    )
    if runtime_dev.is_dir() and (runtime_dev / "manifest.json").is_file():
        return runtime_dev
    dev = source_root / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
    if dev.is_dir() and (dev / "manifest.json").is_file():
        return dev
    _ = target
    raise FileNotFoundError(f"no Published Contract Bundle found under {source_root}")


__all__ = ["resolve_bundle_dir"]
