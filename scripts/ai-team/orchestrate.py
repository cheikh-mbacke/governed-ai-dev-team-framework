#!/usr/bin/env python3
"""Orchestrator CLI — the one real long-running process in this codebase.

Thin wrapper around `run_scheduling_tick` (fully unit-tested, see
tests/core/test_orchestrator_tick.py). This script itself is not unit
tested: real wall-clock behavior over a real interval is exactly what
docs/framework-design/requirements/mode-nuit-preuve-resilience-couverture.md flags
as needing a real run, not a unit test.

`adapters/cursor/runtime/execute.py::execute_runtime()` launches the native
Cursor agent only after explicit unattended opt-in and a passing preflight.

With `--workers N > 1`, N threads tick concurrently, each under its own
worker id. `CommandGateway.execute_command()` is safe to share across
threads: `ProjectLock` (core/persistence/lock.py) serializes the actual
writes at the filesystem level via an atomic O_CREAT|O_EXCL lock file, and
every Run-scoped write is already protected by optimistic concurrency
(Work Unit/Run revisions) or fencing (lease epochs) — a losing thread gets
a harmless CONFLICT, never corrupted state. `run_scheduling_tick` itself
only ever dispatches execution attempts for leases the calling worker_id
already holds (Document 6 §11), so two workers never race on the same
Work Unit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime, import_adapters_cursor

bootstrap_runtime(_REPO_ROOT)

from governed_ai.compat.datetime import UTC, datetime
from governed_ai.core.commands.errors import (
    GatewayError,
    exit_code_for,
)
from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.domain.run.autonomy_policy import is_unattended_preset
from governed_ai.core.orchestrator.progress import evaluate_run_progress
from governed_ai.core.orchestrator.tick import run_scheduling_tick
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed
from governed_ai.notifications.service import dispatch_notifications

_print_lock = threading.Lock()


def _process_record_path(workspace: Workspace, run_id: str) -> Path:
    return workspace.ai_team / "runs" / "processes" / f"{run_id}.json"


def _write_process_record(
    workspace: Workspace,
    run_id: str,
    *,
    status: str,
    worker_ids: list[str],
    last_action: str | None = None,
) -> None:
    path = _process_record_path(workspace, run_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    run_path = workspace.ai_team / "runs" / f"{run_id}.yaml"
    progress = None
    try:
        import yaml

        run_document = yaml.safe_load(run_path.read_text(encoding="utf-8")) or {}
        progress = evaluate_run_progress(workspace.ai_team, run_document)
    except (OSError, yaml.YAMLError):
        progress = {"state": "unknown"}
    document = {
        "run_id": run_id,
        "pid": os.getpid(),
        "status": status,
        "heartbeat_at": datetime.now(UTC).isoformat(),
        "worker_ids": worker_ids,
        "last_action": last_action,
        "progress": progress,
    }
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        # Operational telemetry must never become a new scheduler failure.
        pass


def _close_run_after_process_failure(
    gateway: CommandGateway,
    workspace: Workspace,
    run_id: str,
    errors: list[str],
) -> bool:
    import yaml

    run_path = workspace.ai_team / "runs" / f"{run_id}.yaml"
    try:
        run_document = yaml.safe_load(run_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    if run_document.get("status") != "active":
        return True
    token = uuid.uuid4().hex
    receipt, exit_code = gateway.execute_command(
        {
            "protocol_version": "1.0",
            "command_id": f"CMD-orchestrator-failure-{token}",
            "idempotency_key": f"idem-orchestrator-failure-{token}",
            "correlation_id": run_id,
            "type": "CloseRun",
            "issued_at": datetime.now(UTC).isoformat(),
            "actor": {
                "kind": "role",
                "execution_id": f"EXE-orchestrator-failure-{token[:8]}",
                "role_id": "control-plane",
                "bundle_version": "1.0.0",
                "adapter_id": "cursor",
            },
            "target": {
                "kind": "run",
                "id": run_id,
                "expected_revision": run_document["revision"],
            },
            "payload": {
                "status": "failed",
                "reason": "; ".join(errors)[:2000],
                "stop_condition": "orchestrator_process_failure",
            },
        }
    )
    if exit_code != 0:
        print(f"Unable to close failed Run: {receipt.get('errors')}", file=sys.stderr)
        return False
    dispatch_notifications(workspace, include_digest=True)
    return True


def _start_watchdog(
    workspace: Workspace,
    run_id: str,
    *,
    workers: int,
    interval_seconds: float,
) -> None:
    command = [
        sys.executable,
        str(workspace.root / "scripts" / "ai-team" / "night_watchdog.py"),
        "--run-id",
        run_id,
        "--interval-seconds",
        str(max(5.0, interval_seconds)),
        "--workers",
        str(workers),
        "--launch",
    ]
    environment = dict(os.environ)
    environment["GOVERNED_AI_WATCHDOG_CHILD"] = "1"
    kwargs: dict = {
        "cwd": str(workspace.root),
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def _worker_loop(
    *,
    gateway: CommandGateway,
    workspace: Workspace,
    adapter,
    run_id: str,
    worker_id: str,
    all_worker_ids: list[str],
    interval_seconds: float,
    max_ticks: int | None,
    stop_event: threading.Event,
    errors: list[str],
) -> None:
    tick_count = 0
    while not stop_event.is_set() and (max_ticks is None or tick_count < max_ticks):
        try:
            result = run_scheduling_tick(
                gateway, workspace, run_id=run_id, adapter=adapter, worker_id=worker_id
            )
            with _print_lock:
                print(
                    f"[{worker_id} tick {tick_count}] {result.action} "
                    f"work_unit={result.work_unit_id} {result.details}"
                )
                _write_process_record(
                    workspace,
                    run_id,
                    status="running",
                    worker_ids=all_worker_ids,
                    last_action=result.action,
                )
            terminal = result.action in {"run_completed", "run_stopped", "run_not_active"}
            notification_result = dispatch_notifications(
                workspace,
                include_digest=terminal,
            )
            if notification_result.get("failed"):
                with _print_lock:
                    print(
                        f"[{worker_id}] notification delivery deferred: "
                        f"{notification_result['failed']} failure(s)",
                        file=sys.stderr,
                    )
            if terminal:
                stop_event.set()
                return
        except Exception as exc:  # noqa: BLE001 - a worker failure must stop the session
            with _print_lock:
                print(f"[{worker_id} tick {tick_count}] ERROR: {exc}", file=sys.stderr)
                errors.append(f"{worker_id}: {type(exc).__name__}: {exc}")
            stop_event.set()
            return
        tick_count += 1
        if max_ticks is not None and tick_count >= max_ticks:
            return
        stop_event.wait(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Run id to schedule, e.g. RUN-2026-08-30")
    parser.add_argument("--worker-id", default="orchestrator-worker")
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of concurrent worker threads"
    )
    parser.add_argument(
        "--interval-seconds", type=float, default=60.0, help="Delay between ticks"
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Stop each worker after this many ticks (default: run forever)",
    )
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Do not start the independent recovery watchdog",
    )
    parser.add_argument(
        "--watchdog-interval-seconds",
        type=float,
        default=60.0,
        help="Independent watchdog polling interval",
    )
    args = parser.parse_args(argv)

    workspace = Workspace.discover(Path.cwd())
    try:
        ensure_client_cycle_allowed(workspace)
    except GatewayError as exc:
        print(exc.message, file=sys.stderr)
        return exit_code_for(exc.code)

    agent_cli = import_adapters_cursor("runtime.agent_cli")

    from governed_ai.adapters.cursor.adapter import CursorAdapter
    from governed_ai.contracts.compatibility import resolve_active_bundle_dir

    gateway = CommandGateway(workspace)
    run_path = workspace.ai_team / "runs" / f"{args.run_id}.yaml"
    if not run_path.is_file():
        print(f"Run not found: {run_path}", file=sys.stderr)
        return 2
    import yaml

    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8")) or {}
    if (
        is_unattended_preset(run_document.get("autonomy_preset"))
        and not agent_cli.is_real_agent_launch_enabled()
    ):
        print(
            "Unattended orchestration refused: native Cursor agent launch is disabled. "
            "Set GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH=1 and regenerate a passing preflight.",
            file=sys.stderr,
        )
        return 3
    bundle_dir = resolve_active_bundle_dir(workspace.ai_team / "contracts")
    adapter = CursorAdapter(project_root=workspace.root, bundle_dir=bundle_dir)

    stop_event = threading.Event()
    worker_errors: list[str] = []
    worker_ids = (
        [args.worker_id]
        if args.workers == 1
        else [f"{args.worker_id}-{i}" for i in range(args.workers)]
    )
    threads = [
        threading.Thread(
            target=_worker_loop,
            kwargs={
                "gateway": gateway,
                "workspace": workspace,
                "adapter": adapter,
                "run_id": args.run_id,
                "worker_id": worker_id,
                "all_worker_ids": worker_ids,
                "interval_seconds": args.interval_seconds,
                "max_ticks": args.max_ticks,
                "stop_event": stop_event,
                "errors": worker_errors,
            },
            name=worker_id,
        )
        for worker_id in worker_ids
    ]

    _write_process_record(
        workspace,
        args.run_id,
        status="starting",
        worker_ids=worker_ids,
    )
    if (
        not args.no_watchdog
        and args.max_ticks is None
        and is_unattended_preset(run_document.get("autonomy_preset"))
        and os.environ.get("GOVERNED_AI_WATCHDOG_CHILD") != "1"
    ):
        _start_watchdog(
            workspace,
            args.run_id,
            workers=args.workers,
            interval_seconds=args.watchdog_interval_seconds,
        )

    for thread in threads:
        thread.start()
    interrupted = False
    try:
        for thread in threads:
            while thread.is_alive():
                thread.join(timeout=0.5)
    except KeyboardInterrupt:
        interrupted = True
        stop_event.set()
        for thread in threads:
            thread.join()

    if worker_errors:
        _close_run_after_process_failure(gateway, workspace, args.run_id, worker_errors)
    _write_process_record(
        workspace,
        args.run_id,
        status="interrupted" if interrupted else "failed" if worker_errors else "exited",
        worker_ids=worker_ids,
        last_action="orchestrator_process_failure" if worker_errors else None,
    )
    return 1 if worker_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
