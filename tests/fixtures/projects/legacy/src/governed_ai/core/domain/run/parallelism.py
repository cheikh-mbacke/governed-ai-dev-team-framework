"""Worker parallelism cap (Document 6 §11 `execution.maximum_parallel_workers`).

Distinct from execution_ceiling (what a Work Unit may do) and convergence
bounds (how many attempts a step gets): this caps how many Work Units may
have an active worker lease on a Run at once, mechanically enforced at
lease acquisition — not left to how many orchestrator threads happen to
be started.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAXIMUM_PARALLEL_WORKERS = 4


def active_worker_count(run_document: dict[str, Any]) -> int:
    """Count Work Units currently holding an active lease on this Run.

    `leases_by_work_unit` always points at the *current* lease per Work
    Unit — reassignment overwrites the entry rather than adding to it — so
    its length is exactly the number of workers active right now.
    """
    return len(run_document.get("leases_by_work_unit") or {})
