"""Cursor adapter runtime — RuntimeResult collection and Cursor diagnostics."""

from .checks import collect_preflight_report, last_hook_activity
from .execute import collect_runtime_result, execute_runtime
from .results import runtime_results_dir

__all__ = [
    "collect_preflight_report",
    "collect_runtime_result",
    "execute_runtime",
    "last_hook_activity",
    "runtime_results_dir",
]
