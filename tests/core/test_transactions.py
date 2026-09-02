"""TX-001, TX-002, TX-003, TX-007, TX-008 — transaction commit failpoints."""

from __future__ import annotations

import json
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from governed_ai.core.commands.errors import ErrorCode, GatewayError
from governed_ai.core.domain.gates.naming import generate_gate_decision_id
from governed_ai.core.persistence.atomic import set_write_failure_hook
from governed_ai.core.persistence.failpoints import (
    Failpoint,
    TransactionFailpointError,
    activate_failpoint,
    clear_failpoints,
)
from governed_ai.core.persistence.lock import acquire_project_lock
from governed_ai.core.persistence.transaction import Transaction, recover_transactions

FIXED_TIME = datetime(2026, 8, 29, 19, 30, 0, 123456, tzinfo=UTC)


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
    (observations / "OBS-B.yaml").write_text(
        yaml.safe_dump({"id": "OBS-B", "symptom": "before-b"}),
        encoding="utf-8",
    )
    return workspace, transactions


@pytest.fixture(autouse=True)
def _reset_failpoints() -> None:
    clear_failpoints()
    set_write_failure_hook(None)
    yield
    clear_failpoints()
    set_write_failure_hook(None)


def _snapshot(workspace: Path, relative_paths: list[str]) -> dict[str, str]:
    return {
        rel: (workspace / rel).read_text(encoding="utf-8")
        for rel in relative_paths
        if (workspace / rel).is_file()
    }


def test_tx001_stop_before_first_replacement_state_intact_after_recovery(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    rel_paths = [".ai-team/observations/OBS-A.yaml"]
    before = _snapshot(workspace, rel_paths)

    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "after-a"},
    )
    activate_failpoint(Failpoint.BEFORE_JOURNAL)
    with pytest.raises(TransactionFailpointError):
        transaction.commit()

    assert _snapshot(workspace, rel_paths) == before
    assert not transaction.journal_path.is_file()
    recover_transactions(transactions, workspace)
    assert _snapshot(workspace, rel_paths) == before


def test_tx002_stop_between_two_aggregates_recovery_completes_both(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "after-a"},
    )
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-B.yaml",
        {"id": "OBS-B", "symptom": "after-b"},
    )
    activate_failpoint(Failpoint.AFTER_REPLACE, index=0)
    with pytest.raises(TransactionFailpointError):
        transaction.commit()

    assert yaml.safe_load((workspace / ".ai-team/observations/OBS-A.yaml").read_text())["symptom"] == "after-a"
    assert yaml.safe_load((workspace / ".ai-team/observations/OBS-B.yaml").read_text())["symptom"] == "before-b"

    recover_transactions(transactions, workspace)
    assert yaml.safe_load((workspace / ".ai-team/observations/OBS-A.yaml").read_text())["symptom"] == "after-a"
    assert yaml.safe_load((workspace / ".ai-team/observations/OBS-B.yaml").read_text())["symptom"] == "after-b"


def test_tx003_stop_before_domain_events_completed_once_by_recovery(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    event_path = workspace / ".ai-team/events/domain/EVT-TX003.json"
    event_doc = {
        "event_id": "EVT-TX003",
        "event_type": "ObservationRecorded",
        "event_version": 1,
        "occurred_at": "2026-08-29T19:30:00Z",
        "transaction_id": "pending",
        "correlation_id": "COR-TX003",
        "aggregate": {"kind": "observation", "id": "OBS-A"},
        "data": {"symptom": "after-a"},
    }

    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "after-a"},
    )
    transaction.plan_domain_event(event_path, event_doc)
    activate_failpoint(Failpoint.BEFORE_DOMAIN_EVENTS)
    with pytest.raises(TransactionFailpointError):
        transaction.commit()

    assert yaml.safe_load((workspace / ".ai-team/observations/OBS-A.yaml").read_text())["symptom"] == "after-a"
    assert not event_path.is_file()

    recover_transactions(transactions, workspace)
    assert json.loads(event_path.read_text(encoding="utf-8"))["event_id"] == "EVT-TX003"

    recover_transactions(transactions, workspace)
    assert json.loads(event_path.read_text(encoding="utf-8"))["event_id"] == "EVT-TX003"


def test_tx005_lock_already_held_timeout_no_writes(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    lock_path = workspace / ".ai-team/locks/project.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held = acquire_project_lock(lock_path, timeout_seconds=0.05)
    try:
        with pytest.raises(GatewayError) as exc:
            acquire_project_lock(lock_path, timeout_seconds=0.05)
        assert exc.value.code == ErrorCode.CONFLICT
    finally:
        held.release()

    before = (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8")
    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "should-not-write"},
    )
    transaction.commit()
    assert (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8") != before


def test_tx007_two_gate_decisions_same_microsecond_have_unique_names() -> None:
    with patch("governed_ai.core.domain.gates.naming.datetime") as mocked:
        mocked.now.return_value = FIXED_TIME
        mocked.side_effect = lambda *args, **kwargs: datetime.now(UTC)
        first = generate_gate_decision_id("G2")
        second = generate_gate_decision_id("G2")
    assert first != second
    assert first.startswith("gate-g2-20260829T193000123456-")


def test_tx008_simulated_write_failure_leaves_recoverable_state(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    target = workspace / ".ai-team/observations/OBS-A.yaml"
    before = target.read_text(encoding="utf-8")
    deny_count = {"value": 0}

    def deny_replace(path: Path) -> None:
        if path.resolve() == target.resolve():
            deny_count["value"] += 1
            raise OSError(13, "Permission denied")

    set_write_failure_hook(deny_replace)
    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(target, {"id": "OBS-A", "symptom": "blocked"})
    try:
        with pytest.raises(OSError):
            transaction.commit()
    finally:
        set_write_failure_hook(None)

    assert deny_count["value"] == 1
    assert target.read_text(encoding="utf-8") == before
    journal_path = transaction.journal_path
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "prepared"
    recover_transactions(transactions, workspace)
    assert yaml.safe_load(target.read_text())["symptom"] == "blocked"


def test_tx008_write_failure_before_journal_leaves_initial_state(tx_root: tuple[Path, Path]) -> None:
    workspace, transactions = tx_root
    before = (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8")

    transaction = Transaction.begin(transactions)
    transaction.plan_yaml_write(
        workspace / ".ai-team/observations/OBS-A.yaml",
        {"id": "OBS-A", "symptom": "never"},
    )

    def deny_journal(path: Path) -> None:
        if path.resolve() == transaction.journal_path.resolve():
            raise OSError(28, "No space left on device")

    set_write_failure_hook(deny_journal)
    with pytest.raises(OSError):
        transaction.commit()

    assert (workspace / ".ai-team/observations/OBS-A.yaml").read_text(encoding="utf-8") == before
    assert not transaction.journal_path.is_file()
