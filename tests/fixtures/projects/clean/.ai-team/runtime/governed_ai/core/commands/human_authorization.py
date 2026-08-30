"""Human authorization consumption for gateway commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governed_ai.core.persistence.transaction import Transaction


def consume_human_authorization(
    envelope: dict[str, Any],
    *,
    workspace_ai_team: Path,
    transaction: Transaction,
) -> None:
    auth = envelope["human_authorization"]
    auth_id = auth["authorization_id"]
    path = workspace_ai_team / "authorizations" / f"{auth_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
    else:
        record = dict(auth)
    record["consumed_at"] = datetime.now(UTC).isoformat()
    transaction.plan_json_write(path, record)
