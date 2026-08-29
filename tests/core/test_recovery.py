"""TX-004, TX-006, TX-009 — recovery idempotence and journal integrity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.persistence.failpoints import Failpoint, TransactionFailpointError, activate_failpoint, clear_failpoints
from governed_ai.core.persistence.transaction import Transaction, recover_transactions


@pytest.fixture(autouse=True)
def _reset_failpoints() -> None:
    clear_failpoints()
    yield
    clear_failpoints()


@pytest.fixture()
def tx_root(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "project"
    ai_team = workspace / ".ai-team"
    transactions = ai_team / ".transactions"
    observations = ai_team / "observations"
    events_domain = ai_team / "events" / "domain"
    for directory in (transactions, observations, events_domain):
        directory.mkdir(parents=True)
    (observations / "OBS-A.yaml").write_text(
        yaml.safe_dump({"id": "OBS-A", "symptom": "before-a"}),
        encoding="utf-8",
    )
    return workspace, transactions


def test_tx004_double_recovery_is_idempotent(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "after-a"},
    )
    transaction.commit()

    first = recover_transactions(transactions, workspace)
    second = recover_transactions(transactions, workspace)
    assert first == []
    assert second == []
    assert yaml.safe_load((workspace / ".ai-team/observations/OBS-A.yaml").read_text())["symptom"] == "after-a"


def test_tx006_tampered_journal_hash_requires_manual_recovery(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "after-a"},
    )
    activate_failpoint(Failpoint.AFTER_JOURNAL)
    with pytest.raises(TransactionFailpointError):
        transaction.commit()

    journal_path = transaction.journal_path
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["writes"][0]["after_hash"] = "0" * 64
    journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(GatewayError) as exc:
        recover_transactions(transactions, workspace)
    assert exc.value.code == ErrorCode.TRANSACTION_RECOVERY_REQUIRED
    assert (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8") == yaml.safe_dump(
        {"id": "OBS-A", "symptom": "before-a"},
        sort_keys=False,
    )


def test_tx009_invalid_partial_journal_returns_initial_state(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    before = (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8")
    tx_dir = transactions / "TX-partial"
    tx_dir.mkdir(parents=True)
    (tx_dir / "journal.json").write_text('{"transaction_id": "TX-partial", "status": "prep', encoding="utf-8")

    messages = recover_transactions(transactions, workspace)
    assert any("removed invalid journal" in message for message in messages)
    assert (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8") == before
    assert not (tx_dir / "journal.json").is_file()


def test_tx009_truncated_journal_after_journal_write_no_speculative_repair(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "after-a"},
    )
    activate_failpoint(Failpoint.AFTER_JOURNAL)
    with pytest.raises(TransactionFailpointError):
        transaction.commit()

    before = (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8")
    transaction.journal_path.write_text("{", encoding="utf-8")
    recover_transactions(transactions, workspace)
    assert (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8") == before
