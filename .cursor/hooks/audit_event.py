#!/usr/bin/env python3
"""Append privacy-minimized Cursor events to the active local audit journal."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
MAX_LOG_BYTES = 10 * 1024 * 1024
ROTATED_LOGS = 3


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _read_payload() -> tuple[dict[str, Any], dict[str, Any] | None]:
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8-sig", errors="replace")
    if not raw.strip():
        return {}, {"reason": "empty", "byte_count": len(raw_bytes), "sha256": _digest(raw)}
    try:
        value = json.loads(raw)
    except Exception:
        return {}, {"reason": "invalid_json", "byte_count": len(raw_bytes), "sha256": _digest(raw)}
    if not isinstance(value, dict):
        return {}, {"reason": "non_object", "byte_count": len(raw_bytes), "sha256": _digest(raw)}
    return value, None


def _relative_path(value: object, root: Path) -> str | None:
    if not value:
        return None
    try:
        return Path(str(value)).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return None


def _first_token(command: str) -> str | None:
    stripped = command.strip()
    if not stripped:
        return None
    token = stripped.split(maxsplit=1)[0].strip('"\'')
    return Path(token).name[:80] or None


def _safe_event(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    safe: dict[str, Any] = {
        "hook_event_name": payload.get("hook_event_name") or payload.get("event_name") or "unknown",
    }
    for key in ("duration", "duration_ms", "exit_code", "status", "model", "sandbox", "tool_name"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
    command = payload.get("command")
    if isinstance(command, str):
        safe["command"] = {
            "executable": _first_token(command),
            "character_count": len(command),
            "sha256": _digest(command),
        }
    output = payload.get("output")
    if isinstance(output, str):
        safe["output"] = {
            "byte_count": len(output.encode("utf-8", errors="replace")),
            "sha256": _digest(output),
        }
    for key in ("session_id", "conversation_id", "generation_id"):
        if payload.get(key):
            safe[f"{key}_ref"] = _digest(str(payload[key]))[:31]
    relative_cwd = _relative_path(payload.get("cwd"), root)
    if relative_cwd is not None:
        safe["cwd"] = relative_cwd
    return safe


def _rotate(path: Path, retention_days: int) -> None:
    if not path.is_file():
        return
    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    if path.stat().st_size < MAX_LOG_BYTES and path.stat().st_mtime >= cutoff:
        return
    oldest = path.with_name(f"{path.name}.{ROTATED_LOGS}")
    if oldest.exists():
        oldest.unlink()
    for index in range(ROTATED_LOGS - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def _telemetry_settings(root: Path) -> tuple[str, int]:
    profile = (
        root / ".fabric" / "project-profile.yaml"
        if (root / ".fabric" / "project-profile.yaml").is_file()
        else root / ".ai-team" / "project-profile.yaml"
    )
    collection = "local_only"
    retention_days = 30
    if not profile.is_file():
        return collection, retention_days
    in_telemetry = False
    try:
        for line in profile.read_text(encoding="utf-8").splitlines():
            if line == "telemetry:":
                in_telemetry = True
                continue
            if in_telemetry and line and not line.startswith(" "):
                break
            if not in_telemetry:
                continue
            stripped = line.strip()
            if stripped.startswith("collection:"):
                collection = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("raw_log_retention_days:"):
                retention_days = max(1, int(stripped.split(":", 1)[1].strip()))
    except (OSError, ValueError):
        pass
    return collection, retention_days


def _prune_rotated_logs(log_dir: Path, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    for path in log_dir.glob("cursor-events.jsonl.*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()


payload, parse_error = _read_payload()
root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
collection, retention_days = _telemetry_settings(root)
if collection == "disabled":
    print(json.dumps({"permission": "allow"}))
    raise SystemExit(0)
record: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "event_id": f"CURSOR-{uuid.uuid4().hex}",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "adapter": {"id": "cursor", "version": os.environ.get("CURSOR_VERSION")},
    "context": {
        key: value
        for key, value in {
            "execution_id": os.environ.get("GOVERNED_AI_EXECUTION_ID"),
            "run_id": os.environ.get("GOVERNED_AI_RUN_ID"),
            "work_unit_id": os.environ.get("GOVERNED_AI_WORK_UNIT_ID"),
            "role_id": os.environ.get("GOVERNED_AI_ROLE_ID"),
        }.items()
        if value
    },
    "event": _safe_event(payload, root),
}
if parse_error is not None:
    record["parse_error"] = parse_error

try:
    if (root / ".fabric" / "project-profile.yaml").is_file():
        log_dir = root / ".fabric" / "logs"
    else:
        log_dir = root / ".ai-team" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "cursor-events.jsonl"
    _rotate(log_path, retention_days)
    _prune_rotated_logs(log_dir, retention_days)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
except Exception:
    pass

print(json.dumps({"permission": "allow"}))
