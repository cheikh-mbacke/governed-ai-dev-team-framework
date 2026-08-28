# ruff: noqa: F401, I001
"""Negative fixture: intentional forbidden imports (not production code)."""

import adapters.cursor  # type: ignore
import distribution  # type: ignore
from governed_ai import distribution as dist  # type: ignore
from governed_ai.adapters.cursor import compile_manifest  # type: ignore
