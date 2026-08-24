#!/usr/bin/env python3
"""Answer 'is anything actually waiting on me, and what happened last?'

Run this before stopping and restarting anything. It never modifies state.
"""
from pathlib import Path
from datetime import datetime, timezone
import json

try:
    import yaml
except ModuleNotFoundError:
    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"


def load_yaml(p):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


print("Governed AI Team diagnosis")
print("=" * 26)
print()
print("Before anything below: scroll up in the Cursor chat and check for a")
print("pending command-approval prompt (a 'Run' / 'Approve' button waiting")
print("for a click). This script cannot see that state - Cursor suspends the")
print("agent before it can write anything this script could read. It is the")
print("single most common invisible-stall cause; check it first.")

# 1. Anything explicitly waiting on a human?
open_human_events = []
events_dir = AI / "events"
if events_dir.exists():
    for p in sorted(events_dir.glob("*.yaml")):
        ev = load_yaml(p)
        if not ev:
            continue
        if ev.get("status") == "open" and ev.get("requires_human"):
            open_human_events.append((p.name, ev))

if open_human_events:
    print("\nACTION NEEDED — open events waiting on a human:")
    for fname, ev in open_human_events:
        print(f"  [{ev.get('type', '?')}] {fname} — {ev.get('summary', '(no summary)')}")
        if ev.get("work_unit"):
            print(f"      Work Unit: {ev['work_unit']}")
else:
    print("\nNo open event is explicitly marked as requiring human input.")
    print("If something still looks stuck, that itself is worth noting — see below.")

# 2. Work Units that are neither ready nor done — where is the work actually sitting?
wu_dir = AI / "work-units"
in_flight = []
if wu_dir.exists():
    for p in sorted(wu_dir.glob("*.yaml")):
        wu = load_yaml(p)
        if not wu:
            continue
        status = wu.get("status")
        if status not in ("done", "cancelled", "ready", None):
            in_flight.append((p.stem, status))

if in_flight:
    print("\nWork Units currently in flight (not ready, not done):")
    for wu_id, status in in_flight:
        print(f"  {wu_id}: {status}")

# 3. When did anything last actually happen?
log_path = AI / "logs" / "cursor-events.jsonl"
if log_path.exists():
    last_line = None
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line
    if last_line:
        try:
            record = json.loads(last_line)
            ts = record.get("timestamp")
            if ts:
                last_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - last_dt
                minutes = int(delta.total_seconds() // 60)
                print(f"\nLast recorded Cursor hook activity: {minutes} minute(s) ago ({ts}).")
                event_kind = None
                inner = record.get("event")
                if isinstance(inner, dict):
                    event_kind = inner.get("hook_event_name") or inner.get("event")
                if event_kind:
                    print(f"  (last event type: {event_kind})")
        except Exception:
            print("\nCould not parse the last log line's timestamp.")
else:
    print("\nNo .ai-team/logs/cursor-events.jsonl yet — no Cursor hook activity recorded.")

print()
if open_human_events:
    print("Next step: resolve the event(s) above, then continue — no need to restart anything.")
elif in_flight:
    print("Next step: nothing is explicitly asking for you, but Work Units are mid-flight.")
    print("If Cursor's own UI shows a subagent stalled with no recent hook activity above,")
    print("that's a real stall with no recorded reason. See docs/OPERATOR_GUIDE.md")
    print("(section 'If it looks stuck') before stopping/restarting.")
else:
    print("Nothing appears in flight or waiting on you.")
