#!/usr/bin/env python3
"""Append Cursor hook events to .ai-team/logs/cursor-events.jsonl.

The hook is deliberately fail-open for logging failures: governance logging should
not unexpectedly break development. Hazardous command blocking lives in guard_shell.py.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read_payload():
    """Read stdin once, then parse.

    Calling ``json.load(sys.stdin)`` and, on failure, ``sys.stdin.read()`` leaves
    an empty ``raw`` because the failed parse already consumed the stream. That
    shows up as ``event: {raw: ""}`` in the log and hides hook types.
    """
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8-sig", errors="replace")
    if not raw.strip():
        return {"raw": raw}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


payload = _read_payload()

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
log_dir = root / ".ai-team" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "cursor_version": os.environ.get("CURSOR_VERSION"),
    "event": payload,
}
try:
    with (log_dir / "cursor-events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
except Exception:
    pass

print(json.dumps({"permission": "allow"}))
