"""RuntimeResult persistence under ``.ai-team/runtime-results/`` — Claude Code binding.

Thin wrapper over ``governed_ai.adapters.common.results``, binding it to this
Adaptateur's own ``ADAPTER_ID``/``ADAPTER_VERSION``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governed_ai.adapters.common.results import (
    EXECUTION_ID_RE,
    FENCED_JSON_RE,
    HANDOFF_DIAGNOSTIC_MAX,
    HANDOFF_SUMMARY_MAX,
    RUNTIME_RESULTS_DIR,
    SHA40_RE,
    extract_governed_handoff,
    is_conforming_governed_handoff,
    result_path,
    runtime_results_dir,
    utc_now_iso,
)
from governed_ai.adapters.common.results import (
    build_runtime_result as _build_runtime_result,
)
from governed_ai.adapters.common.results import (
    load_runtime_result as _load_runtime_result,
)
from governed_ai.adapters.common.results import (
    persist_runtime_result as _persist_runtime_result,
)
from governed_ai.adapters.common.results import (
    validate_runtime_result as _validate_runtime_result,
)
from governed_ai.adapters.spi import ExecutionRequest, RuntimeResult

from ..compiler.compile import ADAPTER_ID, ADAPTER_VERSION


def validate_runtime_result(result: dict[str, Any]) -> list[str]:
    return _validate_runtime_result(result, expected_adapter_id=ADAPTER_ID)


def build_runtime_result(request: ExecutionRequest, **kwargs: Any) -> RuntimeResult:
    return _build_runtime_result(
        request,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        **kwargs,
    )


def persist_runtime_result(project_root: Path, result: RuntimeResult) -> Path:
    return _persist_runtime_result(project_root, result, expected_adapter_id=ADAPTER_ID)


def load_runtime_result(project_root: Path, execution_id: str) -> RuntimeResult:
    return _load_runtime_result(project_root, execution_id, expected_adapter_id=ADAPTER_ID)


__all__ = [
    "EXECUTION_ID_RE",
    "FENCED_JSON_RE",
    "HANDOFF_DIAGNOSTIC_MAX",
    "HANDOFF_SUMMARY_MAX",
    "RUNTIME_RESULTS_DIR",
    "SHA40_RE",
    "build_runtime_result",
    "extract_governed_handoff",
    "is_conforming_governed_handoff",
    "load_runtime_result",
    "persist_runtime_result",
    "result_path",
    "runtime_results_dir",
    "utc_now_iso",
    "validate_runtime_result",
]
