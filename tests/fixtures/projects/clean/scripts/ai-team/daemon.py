#!/usr/bin/env python3
"""Supervisor daemon CLI — persistent owner of unattended Run scheduling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.supervisor.daemon import (
    SupervisorDaemon,
    register_run,
    spawn_background,
    unregister_run,
)
from governed_ai.core.supervisor.instance_lock import InstanceLockError, read_instance_status
from governed_ai.core.supervisor.status import build_doctor, build_status, format_status_text
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed


def _workspace() -> Workspace:
    workspace = Workspace.discover(Path.cwd())
    try:
        ensure_client_cycle_allowed(workspace)
    except GatewayError as exc:
        print(exc.message, file=sys.stderr)
        raise SystemExit(exit_code_for(exc.code)) from None
    return workspace


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(format_status_text(payload))


def cmd_start(args: argparse.Namespace) -> int:
    workspace = _workspace()
    existing = read_instance_status(workspace.ai_team)
    if existing.get("state") == "running":
        print(
            json.dumps(
                {
                    "outcome": "already_running",
                    "instance": existing.get("instance"),
                },
                ensure_ascii=False,
            )
        )
        return 1
    result = spawn_background(workspace, interval_seconds=args.interval_seconds)
    print(json.dumps({"outcome": "started", **result}, ensure_ascii=False))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    workspace = _workspace()
    daemon = SupervisorDaemon(
        workspace,
        interval_seconds=args.interval_seconds,
    )
    try:
        daemon.acquire()
    except InstanceLockError as exc:
        print(json.dumps({"outcome": "lock_failed", "reason": str(exc)}), file=sys.stderr)
        return 1
    try:
        return daemon.run_forever(max_cycles=args.max_cycles)
    except KeyboardInterrupt:
        daemon.request_stop()
        daemon.shutdown()
        return 0


def cmd_stop(args: argparse.Namespace) -> int:
    workspace = _workspace()
    status = read_instance_status(workspace.ai_team)
    if status.get("state") != "running":
        print(json.dumps({"outcome": "not_running", **status}, ensure_ascii=False))
        return 0
    pid = int((status.get("instance") or {}).get("pid") or 0)
    if not pid:
        print(json.dumps({"outcome": "no_pid", **status}, ensure_ascii=False))
        return 1
    import os
    import signal

    try:
        if os.name == "nt":
            # CTRL_BREAK_EVENT requires a process group; SIGTERM is unavailable.
            # taskkill without /F requests graceful termination first.
            import subprocess

            subprocess.run(
                ["taskkill", "/PID", str(pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print(json.dumps({"outcome": "signal_failed", "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"outcome": "stop_signalled", "pid": pid}, ensure_ascii=False))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = _workspace()
    payload = build_status(workspace)
    _emit(payload, as_json=args.json)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = _workspace()
    payload = build_doctor(workspace)
    _emit(payload, as_json=args.json)
    return 0 if payload.get("doctor", {}).get("ok") else 2


def cmd_reconcile_once(args: argparse.Namespace) -> int:
    workspace = _workspace()
    daemon = SupervisorDaemon(workspace, interval_seconds=args.interval_seconds)
    try:
        daemon.acquire()
    except InstanceLockError as exc:
        print(json.dumps({"outcome": "lock_failed", "reason": str(exc)}), file=sys.stderr)
        return 1
    try:
        results = daemon.reconcile_once()
        print(json.dumps({"outcome": "ok", "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        daemon.shutdown()


def cmd_register(args: argparse.Namespace) -> int:
    workspace = _workspace()
    entry = register_run(
        workspace,
        args.run_id,
        workers=args.workers,
        max_recoveries=args.max_recoveries,
    )
    print(json.dumps({"outcome": "registered", "entry": entry}, ensure_ascii=False))
    return 0


def cmd_unregister(args: argparse.Namespace) -> int:
    workspace = _workspace()
    removed = unregister_run(workspace, args.run_id)
    print(json.dumps({"outcome": "unregistered" if removed else "missing", "run_id": args.run_id}))
    return 0 if removed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start daemon in background")
    start.add_argument("--interval-seconds", type=float, default=5.0)
    start.set_defaults(func=cmd_start)

    run = sub.add_parser("run", help="Run daemon loop")
    run.add_argument("--foreground", action="store_true", default=True)
    run.add_argument("--interval-seconds", type=float, default=5.0)
    run.add_argument("--max-cycles", type=int, default=None)
    run.set_defaults(func=cmd_run)

    stop = sub.add_parser("stop", help="Signal running daemon to stop")
    stop.set_defaults(func=cmd_stop)

    status = sub.add_parser("status", help="Show daemon and supervised Run status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    doctor = sub.add_parser("doctor", help="Diagnose daemon health")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    reconcile = sub.add_parser("reconcile-once", help="Acquire lock, reconcile once, release")
    reconcile.add_argument("--interval-seconds", type=float, default=5.0)
    reconcile.set_defaults(func=cmd_reconcile_once)

    register = sub.add_parser("register-run", help="Register a Run for supervision")
    register.add_argument("--run-id", required=True)
    register.add_argument("--workers", type=int, default=1)
    register.add_argument("--max-recoveries", type=int, default=3)
    register.set_defaults(func=cmd_register)

    unregister = sub.add_parser("unregister-run", help="Stop supervising a Run")
    unregister.add_argument("--run-id", required=True)
    unregister.set_defaults(func=cmd_unregister)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
