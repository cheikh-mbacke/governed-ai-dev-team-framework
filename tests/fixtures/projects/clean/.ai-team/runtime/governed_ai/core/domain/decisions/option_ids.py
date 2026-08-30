"""Decision option helpers."""

from __future__ import annotations

from typing import Any


def option_ids(options: list[Any]) -> set[str]:
    ids: set[str] = set()
    for option in options:
        if isinstance(option, str):
            ids.add(option)
        elif isinstance(option, dict) and option.get("id"):
            ids.add(str(option["id"]))
    return ids
