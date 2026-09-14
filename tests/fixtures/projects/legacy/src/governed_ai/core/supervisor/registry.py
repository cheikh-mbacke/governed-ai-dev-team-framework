"""Durable supervised-run registry."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.persistence.atomic import atomic_write_text
from governed_ai.core.supervisor.paths import ensure_supervisor_layout, registry_path

REGISTRY_SCHEMA_VERSION = 1


def _empty_registry() -> dict[str, Any]:
    return {"schema_version": REGISTRY_SCHEMA_VERSION, "runs": {}}


def load_registry(ai_team: Path) -> dict[str, Any]:
    path = registry_path(ai_team)
    if not path.is_file():
        return _empty_registry()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(document, dict):
        return _empty_registry()
    document.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
    document.setdefault("runs", {})
    if not isinstance(document["runs"], dict):
        document["runs"] = {}
    return document


def save_registry(ai_team: Path, document: dict[str, Any]) -> None:
    ensure_supervisor_layout(ai_team)
    payload = {
        "schema_version": int(document.get("schema_version") or REGISTRY_SCHEMA_VERSION),
        "runs": dict(document.get("runs") or {}),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    atomic_write_text(
        registry_path(ai_team),
        json.dumps(payload, indent=2, sort_keys=True),
    )


def register_run(
    ai_team: Path,
    run_id: str,
    *,
    workers: int = 1,
    max_recoveries: int = 3,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = load_registry(ai_team)
    now = datetime.now(UTC).isoformat()
    entry = deepcopy(document["runs"].get(run_id) or {})
    entry.update(
        {
            "run_id": run_id,
            "registered_at": entry.get("registered_at") or now,
            "updated_at": now,
            "workers": max(1, int(workers)),
            "max_recoveries": max(0, int(max_recoveries)),
            "recovery_count": int(entry.get("recovery_count") or 0),
            "status": "registered",
            "metadata": {**(entry.get("metadata") or {}), **(metadata or {})},
        }
    )
    document["runs"][run_id] = entry
    save_registry(ai_team, document)
    return entry


def unregister_run(ai_team: Path, run_id: str) -> bool:
    document = load_registry(ai_team)
    if run_id not in document["runs"]:
        return False
    del document["runs"][run_id]
    save_registry(ai_team, document)
    return True


def update_run_entry(ai_team: Path, run_id: str, **fields: Any) -> dict[str, Any] | None:
    document = load_registry(ai_team)
    entry = document["runs"].get(run_id)
    if entry is None:
        return None
    entry = dict(entry)
    entry.update(fields)
    entry["updated_at"] = datetime.now(UTC).isoformat()
    document["runs"][run_id] = entry
    save_registry(ai_team, document)
    return entry


def list_registered_runs(ai_team: Path) -> list[dict[str, Any]]:
    document = load_registry(ai_team)
    return [dict(item) for item in document["runs"].values()]
