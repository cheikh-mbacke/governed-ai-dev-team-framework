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

try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {"raw": sys.stdin.read()}

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
