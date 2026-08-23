#!/usr/bin/env python3
"""Optionally back up the current working branch to "origin" after a subagent stops.

Off by default (.ai-team/project-profile.yaml -> release.auto_push_working_branches).
Even when enabled, this refuses to push the protected branch, and never fails the
triggering action if the push itself fails or no remote is configured - a backup
push is a convenience, not a gate. It never merges, force-pushes, or touches any
branch other than the one currently checked out.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    # Consistent with the rest of the framework's dependency handling: don't
    # crash a hook over a missing package, just skip this optional behavior.
    print(json.dumps({"permission": "allow"}))
    raise SystemExit(0)

root = Path(os.environ.get("CURSOR_PROJECT_DIR", ".")).resolve()
profile_path = root / ".ai-team" / "project-profile.yaml"


def allow():
    print('{"permission": "allow"}')
    raise SystemExit(0)


if not profile_path.exists():
    allow()

try:
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
except Exception:
    allow()

release = profile.get("release") or {}
if not release.get("auto_push_working_branches"):
    allow()

protected_branch = release.get("protected_branch", "main")


def run(cmd):
    return subprocess.run(
        cmd, cwd=root, capture_output=True, text=True, timeout=15
    )


try:
    remote = run(["git", "remote", "get-url", "origin"])
    if remote.returncode != 0:
        # No "origin" configured - nothing to back up to. Not an error.
        allow()

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch.returncode != 0:
        allow()
    current_branch = branch.stdout.strip()

    # Defense in depth: don't rely solely on protected_branch being
    # configured correctly. "main" and "master" are refused unconditionally,
    # since almost every git repository's trunk uses one of these two names
    # regardless of what this project's config happens to say - a
    # misconfigured protected_branch must not silently turn into permission
    # to push the real trunk.
    always_refused = {"main", "master", protected_branch}
    if not current_branch or current_branch in always_refused or current_branch == "HEAD":
        allow()

    run(["git", "push", "origin", current_branch])
except Exception:
    # A failed backup push must never block or fail the agent's actual work.
    pass

allow()
