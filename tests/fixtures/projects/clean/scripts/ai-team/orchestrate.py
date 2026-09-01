#!/usr/bin/env python3
"""Orchestrator CLI — the one real long-running process in this codebase.

Thin wrapper around `run_scheduling_tick` (fully unit-tested, see
tests/core/test_orchestrator_tick.py). This script itself is not unit
tested: real wall-clock behavior over a real interval is exactly what
docs/product/requirements/mode-nuit-preuve-resilience-couverture.md flags
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
import sys
import threading
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_REPO_ROOT)

from governed_ai.core.commands.gateway import CommandGateway
from governed_ai.core.orchestrator.tick import run_scheduling_tick
from governed_ai.core.workspace import Workspace

_print_lock = threading.Lock()


def _worker_loop(
    *,
    gateway: CommandGateway,
    workspace: Workspace,
    adapter,
    run_id: str,
    worker_id: str,
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
            if result.action in {"run_completed", "run_stopped", "run_not_active"}:
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
    args = parser.parse_args(argv)

    from adapters.cursor.runtime.agent_cli import is_real_agent_launch_enabled

    from governed_ai.adapters.cursor.adapter import CursorAdapter
    from governed_ai.contracts.compatibility import resolve_active_bundle_dir

    workspace = Workspace.discover(Path.cwd())
    gateway = CommandGateway(workspace)
    run_path = workspace.ai_team / "runs" / f"{args.run_id}.yaml"
    if not run_path.is_file():
        print(f"Run not found: {run_path}", file=sys.stderr)
        return 2
    import yaml

    run_document = yaml.safe_load(run_path.read_text(encoding="utf-8")) or {}
    if (
        str(run_document.get("autonomy_preset", "")).startswith("unattended_")
        and not is_real_agent_launch_enabled()
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
                "interval_seconds": args.interval_seconds,
                "max_ticks": args.max_ticks,
                "stop_event": stop_event,
                "errors": worker_errors,
            },
            name=worker_id,
        )
        for worker_id in worker_ids
    ]

    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            while thread.is_alive():
                thread.join(timeout=0.5)
    except KeyboardInterrupt:
        stop_event.set()
        for thread in threads:
            thread.join()

    return 1 if worker_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
