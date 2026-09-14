#!/usr/bin/env python3
"""Independent liveness/progress watchdog for unattended orchestration.

Compatibility CLI. Prefer the Supervisor Daemon (``daemon.py``) as the
operational owner; this watchdog remains available as an external detector
when the daemon itself is absent.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_ROOT)

from governed_ai.core.supervisor.instance_lock import default_pid_is_alive
from governed_ai.core.supervisor.reconcile import observe_run
from governed_ai.core.workspace import Workspace


def _read_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _invoke_recovery(
    workspace: Workspace,
    run_id: str,
    *,
    max_recoveries: int,
    workers: int,
    launch: bool,
) -> dict:
    command = [
        sys.executable,
        str(workspace.root / "scripts" / "ai-team" / "night_recovery.py"),
        "--run-id",
        run_id,
        "--max-recoveries",
        str(max_recoveries),
        "--workers",
        str(workers),
    ]
    if launch:
        command.append("--launch")
    completed = subprocess.run(
        command,
        cwd=str(workspace.root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return {
            "outcome": "needs_human",
            "run_id": run_id,
            "reason": completed.stderr.strip() or "recovery returned no result",
        }
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {
            "outcome": "needs_human",
            "run_id": run_id,
            "reason": lines[-1],
        }


def inspect(workspace: Workspace, run_id: str) -> dict:
    observation = observe_run(workspace, run_id)
    process_path = workspace.ai_team / "runs" / "processes" / f"{run_id}.json"
    process = _read_json(process_path)
    process_alive = bool(observation.get("process_alive")) or default_pid_is_alive(
        int(process.get("pid") or 0)
    )
    progress = observation.get("progress") or {}
    if observation.get("run_status") != "active":
        action = "terminal"
    elif progress.get("state") == "stalled_no_progress":
        action = "recover"
    elif not process_alive:
        action = "recover"
    else:
        action = "healthy"
    return {
        "run_id": run_id,
        "run_status": observation.get("run_status"),
        "stop_condition": observation.get("stop_condition"),
        "process_alive": process_alive,
        "progress": progress,
        "action": action,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-checks", type=int, default=None)
    parser.add_argument("--max-recoveries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args(argv)
    workspace = Workspace.discover(Path.cwd())
    current_run_id = args.run_id
    checks = 0
    while args.max_checks is None or checks < args.max_checks:
        try:
            report = inspect(workspace, current_run_id)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(json.dumps({"outcome": "needs_human", "reason": str(exc)}))
            return 2
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if report["action"] == "terminal" and report.get("run_status") == "completed":
            return 0
        if report["action"] in {"recover", "terminal"}:
            recovery = _invoke_recovery(
                workspace,
                current_run_id,
                max_recoveries=max(0, args.max_recoveries),
                workers=max(1, args.workers),
                launch=args.launch,
            )
            print(json.dumps(recovery, ensure_ascii=False), flush=True)
            if recovery.get("outcome") != "recovered":
                return 2
            current_run_id = str(recovery["new_run_id"])
        checks += 1
        if args.max_checks is not None and checks >= args.max_checks:
            break
        time.sleep(max(1.0, args.interval_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
