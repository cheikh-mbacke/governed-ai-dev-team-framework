#!/usr/bin/env python3
"""Block obvious hazardous shell operations before execution.

This is a project-level safety net, not a complete security boundary.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Read stdin once (utf-8-sig strips a BOM). Do not json.load then re-read:
# a failed parse consumes the stream and yields an empty payload.
try:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    payload = json.loads(raw) if raw.strip() else {}
except (OSError, UnicodeError, json.JSONDecodeError):
    if os.environ.get("GOVERNED_AI_UNATTENDED_RUN") == "1":
        print(json.dumps({
            "permission": "deny",
            "message": "Malformed hook payload during governed unattended execution.",
        }))
        raise SystemExit(2)
    print(json.dumps({"permission": "allow"}))
    raise SystemExit(0)

blob = json.dumps(payload, ensure_ascii=False)
command = payload.get("command") if isinstance(payload, dict) else None
command = command if isinstance(command, str) else blob


def deny(message):
    print(json.dumps({
        "permission": "deny",
        "message": message,
    }))
    raise SystemExit(2)


def env_json_list(name):
    try:
        value = json.loads(os.environ.get(name, "[]"))
    except json.JSONDecodeError:
        deny(f"Invalid governed unattended configuration: {name}.")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        deny(f"Invalid governed unattended configuration: {name}.")
    return value


if os.environ.get("GOVERNED_AI_UNATTENDED_RUN") == "1":
    allowed_commands = env_json_list("GOVERNED_AI_ALLOWED_SHELL_COMMANDS")
    normalized_command = " ".join(command.strip().split())
    normalized_allowed = {" ".join(item.strip().split()) for item in allowed_commands}
    if normalized_command not in normalized_allowed:
        deny(
            "Shell command is outside the human-approved execution-envelope "
            "allowlist for this unattended Run."
        )

    allowed_paths = env_json_list("GOVERNED_AI_ALLOWED_PATHS")
    if not allowed_paths:
        deny("No writable path was approved for this unattended Run.")
    # Shell commands containing parent traversal are never accepted. Absolute
    # paths are confined to the actual Cursor workspace; finer relative-path
    # scoping remains enforced by the Work Unit scope and isolated worktree.
    if re.search(r"(^|[\\/\s])\.\.([\\/\s]|$)", command):
        deny("Parent-directory traversal is forbidden in unattended shell commands.")
    project_root_for_scope = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
    absolute_tokens = re.findall(
        r"(?<![A-Za-z0-9_.-])(?:[A-Za-z]:[\\/][^\s\"']+|/[^\s\"']+)", command
    )
    for token in absolute_tokens:
        try:
            Path(token).resolve().relative_to(project_root_for_scope)
        except (OSError, ValueError):
            deny("Out-of-workspace absolute path is forbidden in unattended commands.")


def current_branch(project_root):
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={project_root}",
                "rev-parse",
                "--abbrev-ref",
                "HEAD",
            ],
            cwd=project_root,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def read_repository_kind(project_root):
    profile = project_root / ".ai-team" / "project-profile.yaml"
    if not profile.is_file():
        return None
    try:
        text = profile.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("repository_kind:"):
            return stripped.split(":", 1)[1].strip()
    return None


def protected_branches(project_root):
    branches = {"main", "master", "trunk"}
    profile = project_root / ".ai-team" / "project-profile.yaml"
    try:
        text = profile.read_text(encoding="utf-8")
    except OSError:
        return branches
    match = re.search(
        r"(?m)^\s*protected_branch:\s*['\"]?([A-Za-z0-9._/-]+)", text
    )
    if match:
        branches.add(match.group(1))
    return branches


history_rewrite_patterns = [
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+commit\b[^\n]*--amend",
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+rebase\b",
]
for pattern in history_rewrite_patterns:
    if re.search(pattern, command, flags=re.IGNORECASE):
        deny(
            "History rewriting is not an autonomous path. Record evidence impact "
            "and use an explicitly human-authorized workflow."
        )

project_root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
fabrication_mode = read_repository_kind(project_root) == "framework_source"
branch = current_branch(project_root)
protected_mutation = re.search(
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+"
    r"(add|commit|merge|cherry-pick|revert)\b",
    command,
    flags=re.IGNORECASE,
)
if protected_mutation and branch in {None, "HEAD"}:
    if fabrication_mode:
        deny(
            "Git mutation requires a named branch; detached or unresolved HEAD "
            "is not allowed."
        )
    else:
        deny(
            "Git mutation requires a named isolated Work Unit branch; detached or "
            "unresolved HEAD is not an autonomous commit path."
        )
if branch in protected_branches(project_root) and protected_mutation:
    if fabrication_mode:
        deny(
            f"Git mutation '{protected_mutation.group(1)}' is blocked on protected "
            f"branch '{branch}'. Use a short-lived feature branch."
        )
    else:
        deny(
            f"Git mutation '{protected_mutation.group(1)}' is blocked on protected "
            f"branch '{branch}'. Use an isolated Work Unit branch or worktree."
        )

commit_command = re.search(
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+commit\b",
    command,
    flags=re.IGNORECASE,
)
work_unit_message = re.search(
    r"\b[a-z][a-z0-9_-]*\(WU-[A-Za-z0-9._-]+\):\s+\S",
    command,
    flags=re.IGNORECASE,
)
if commit_command and not work_unit_message and not fabrication_mode:
    deny(
        "Autonomous commit messages must use 'type(WU-ID): concise description'. "
        "Use a human-controlled path for commits outside an approved Work Unit."
    )

patterns = [
    r"git\s+push[^\n]*(--force|-f)",
    r"git\s+reset\s+--hard",
    r"git\s+push[^\n]*(main|master|trunk)",
    r"rm\s+-rf\s+/(?:[\s\"']|$)",
    r"kubectl\s+(apply|delete|patch|replace|scale|rollout)",
    r"terraform\s+(apply|destroy)",
    r"\b(prod|production)\b[^\n]*(deploy|migration|migrate|delete|drop|truncate)",
    r"\b(drop\s+database|drop\s+table|truncate\s+table)\b",
]

for pattern in patterns:
    if re.search(pattern, blob, flags=re.IGNORECASE):
        deny(
            "Blocked by governed-ai-team project hook. This operation requires "
            "an explicit human-controlled path/gate."
        )

print(json.dumps({"permission": "allow"}))
