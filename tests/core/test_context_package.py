"""Context Package completeness evaluation."""

from __future__ import annotations

from pathlib import Path

import yaml

from governed_ai.core.orchestrator.context_package import (
    completeness_error,
    evaluate_context_package_completeness,
)


def test_missing_required_contract_marks_incomplete(tmp_path: Path) -> None:
    contract = tmp_path / "contracts" / "shared" / "api.json"
    contract.parent.mkdir(parents=True)
    contract.write_text('{"id":"api"}\n', encoding="utf-8")
    ctx_path = tmp_path / "CTX.yaml"
    document = {
        "id": "CTX-1",
        "work_unit": "WU-1",
        "role": "backend-developer",
        "required_contracts": ["contracts/shared/api.json"],
        "items": [],
        "open_context_requests": [],
    }
    ctx_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    evaluation = evaluate_context_package_completeness(
        workspace_root=tmp_path,
        context_document=document,
        context_path=ctx_path,
        wu_document={"dependencies": []},
    )
    assert evaluation["completeness_status"] == "incomplete"
    assert "contracts/shared/api.json" in evaluation["missing_inputs"]
    assert completeness_error(evaluation)


def test_contract_listed_in_items_is_complete(tmp_path: Path) -> None:
    contract = tmp_path / "contracts" / "shared" / "api.json"
    contract.parent.mkdir(parents=True)
    contract.write_text('{"id":"api"}\n', encoding="utf-8")
    ctx_path = tmp_path / "CTX.yaml"
    document = {
        "id": "CTX-1",
        "work_unit": "WU-1",
        "role": "backend-developer",
        "required_contracts": ["contracts/shared/api.json"],
        "items": [
            {
                "level": "L2_relevant_zone",
                "source": "contracts/shared/api.json",
                "provenance": "authoritative",
                "reason": "shared API",
            }
        ],
        "open_context_requests": [],
    }
    ctx_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    evaluation = evaluate_context_package_completeness(
        workspace_root=tmp_path,
        context_document=document,
        context_path=ctx_path,
        wu_document={"dependencies": []},
    )
    assert evaluation["completeness_status"] == "complete"
    assert evaluation["missing_inputs"] == []
    assert evaluation["source_sha256"] and evaluation["source_sha256"].startswith("sha256:")
    assert completeness_error(evaluation) is None
