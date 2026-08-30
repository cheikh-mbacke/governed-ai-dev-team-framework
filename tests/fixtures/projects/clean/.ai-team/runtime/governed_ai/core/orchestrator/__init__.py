"""Orchestrator — drives Run-scoped Command Gateway commands over time.

Everything under `core/commands/handlers/run_*` and `core/domain/run/` is a
rulebook: it validates and persists state but nothing calls it automatically.
This package is the first real (if minimal) driver of that rulebook.
"""
