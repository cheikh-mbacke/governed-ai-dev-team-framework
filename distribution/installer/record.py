"""Installation Record constants and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEGACY_VERSION_FILE = Path(".ai-team/framework-version.json")
INSTALLATION_RECORD_FILE = Path(".ai-team/installation-record.json")
KNOWN_ADAPTER_IDS = frozenset({"cursor"})


def normalize_path(path: str | Path) -> str:
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def is_v1_manifest(payload: dict[str, Any]) -> bool:
    return payload.get("schema_version") == 1 and isinstance(payload.get("version"), str)


def is_v2_record(payload: dict[str, Any]) -> bool:
    return payload.get("schema_version") == 2 and isinstance(payload.get("project_id"), str)


def is_v3_record(payload: dict[str, Any]) -> bool:
    return payload.get("schema_version") == 3 and isinstance(payload.get("project_id"), str)


def is_installation_record(payload: dict[str, Any]) -> bool:
    return is_v2_record(payload) or is_v3_record(payload)


def read_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def load_legacy_manifest(target: Path) -> dict[str, Any]:
    path = target / LEGACY_VERSION_FILE
    if not path.is_file():
        raise FileNotFoundError(f"missing legacy manifest: {path}")
    payload = read_json_file(path)
    if not is_v1_manifest(payload):
        raise ValueError(f"{path} is not a v1 installation manifest")
    return payload


def load_installation_record(target: Path) -> dict[str, Any] | None:
    path = target / INSTALLATION_RECORD_FILE
    if not path.is_file():
        return None
    payload = read_json_file(path)
    if not is_installation_record(payload):
        raise ValueError(f"{path} is not a supported installation record")
    return payload


def read_installation_manifest(target: Path) -> dict[str, Any]:
    """Return v2/v3 record if present, otherwise legacy v1 manifest."""
    record = load_installation_record(target)
    if record is not None:
        return record
    return load_legacy_manifest(target)


def _paths_from_managed_entries(entries: list[Any]) -> set[str]:
    paths: set[str] = set()
    for entry in entries or []:
        if isinstance(entry, str):
            paths.add(normalize_path(entry))
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            paths.add(normalize_path(entry["path"]))
    return paths


def managed_files_union(record: dict[str, Any]) -> set[str]:
    if is_v2_record(record) or is_v3_record(record):
        files: set[str] = set()
        files.update(_paths_from_managed_entries(record.get("core", {}).get("managed_files")))
        files.update(
            _paths_from_managed_entries(record.get("distribution", {}).get("managed_files"))
        )
        for adapter in record.get("adapters") or []:
            if isinstance(adapter, dict):
                files.update(_paths_from_managed_entries(adapter.get("managed_files")))
        return files
    if is_v1_manifest(record):
        return {normalize_path(p) for p in record.get("managed_files") or []}
    raise ValueError("unsupported installation manifest shape")


def managed_file_hashes(record: dict[str, Any]) -> dict[str, str]:
    """Return path -> installed_sha256 for v3 records; empty for v2."""
    if not is_v3_record(record):
        return {}
    result: dict[str, str] = {}
    sections = [
        record.get("core", {}).get("managed_files"),
        record.get("distribution", {}).get("managed_files"),
    ]
    for adapter in record.get("adapters") or []:
        if isinstance(adapter, dict):
            sections.append(adapter.get("managed_files"))
    for entries in sections:
        for entry in entries or []:
            if isinstance(entry, dict):
                path = entry.get("path")
                digest = entry.get("installed_sha256")
                if isinstance(path, str) and isinstance(digest, str):
                    result[normalize_path(path)] = digest
    return result
