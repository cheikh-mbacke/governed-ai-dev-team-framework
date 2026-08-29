"""Cursor adapter runtime — RuntimeResult collection and Cursor diagnostics."""

from adapters.cursor.runtime.checks import collect_preflight_report, last_hook_activity
from adapters.cursor.runtime.execute import collect_runtime_result, execute_runtime
from adapters.cursor.runtime.results import runtime_results_dir

__all__ = [
    "collect_preflight_report",
    "collect_runtime_result",
    "execute_runtime",
    "last_hook_activity",
    "runtime_results_dir",
]
