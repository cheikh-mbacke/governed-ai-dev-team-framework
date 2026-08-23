#!/usr/bin/env python3
"""Block obvious hazardous shell operations before execution.

This is a project-level safety net, not a complete security boundary.
"""
import json
import re
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    print(json.dumps({"permission": "allow"}))
    raise SystemExit(0)

blob = json.dumps(payload, ensure_ascii=False)
patterns = [
    r"git\s+push[^\n]*(--force|-f)",
    r"git\s+reset\s+--hard",
    r"git\s+push[^\n]*(main|master|trunk)",
    r"rm\s+-rf\s+/(?:\s|$)",
    r"kubectl\s+(apply|delete|patch|replace|scale|rollout)",
    r"terraform\s+(apply|destroy)",
    r"\b(prod|production)\b[^\n]*(deploy|migration|migrate|delete|drop|truncate)",
    r"\b(drop\s+database|drop\s+table|truncate\s+table)\b",
]

for pattern in patterns:
    if re.search(pattern, blob, flags=re.IGNORECASE):
        print(json.dumps({
            "permission": "deny",
            "message": "Blocked by governed-ai-team project hook. This operation requires an explicit human-controlled path/gate."
        }))
        raise SystemExit(2)

print(json.dumps({"permission": "allow"}))
