"""Command receipt builders."""

from __future__ import annotations

from typing import Any

from governed_ai.core.commands.errors import GatewayError


def build_receipt(
    *,
    command_id: str,
    transaction_id: str | None,
    status: str,
    affected: list[dict[str, Any]] | None = None,
    domain_events: list[str] | None = None,
    errors: list[dict[str, str]] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "command_id": command_id,
        "transaction_id": transaction_id,
        "status": status,
        "affected": affected or [],
        "domain_events": domain_events or [],
        "errors": errors or [],
    }
    if details:
        receipt["details"] = details
    return receipt


def build_rejected_receipt(command_id: str, error: GatewayError) -> dict[str, Any]:
    return build_receipt(
        command_id=command_id,
        transaction_id=None,
        status="rejected",
        errors=[error.as_dict()],
    )
