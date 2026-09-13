from pathlib import Path

import yaml

from governed_ai.compat.datetime import UTC, datetime, timedelta
from governed_ai.core.orchestrator.progress import evaluate_run_progress


def _write_yaml(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def test_lease_heartbeat_alone_does_not_mask_stalled_progress(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    old = (now - timedelta(minutes=30)).isoformat()
    run = {
        "id": "RUN-STALL",
        "status": "active",
        "created_at": old,
        "work_unit_ids": ["WU-A"],
        "leases_by_work_unit": {"WU-A": {"lease_id": "LEASE-A", "epoch": 1}},
        "effective_autonomy_policy": {"execution": {"stalled_after_minutes": 15}},
    }
    _write_yaml(
        tmp_path / "work-units" / "WU-A.yaml",
        {"id": "WU-A", "status": "in_progress", "updated_at": old},
    )
    _write_yaml(
        tmp_path / "runs" / "leases" / "LEASE-A.yaml",
        {
            "id": "LEASE-A",
            "run_id": "RUN-STALL",
            "status": "active",
            "heartbeat_at": now.isoformat(),
        },
    )

    report = evaluate_run_progress(tmp_path, run, now=now)
    assert report["state"] == "stalled_no_progress"
    assert report["minutes_without_progress"] == 30.0


def test_started_attempt_is_working_until_its_governed_timeout(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    started = (now - timedelta(minutes=20)).isoformat()
    run = {
        "id": "RUN-WORKING",
        "status": "active",
        "created_at": started,
        "work_unit_ids": ["WU-A"],
        "leases_by_work_unit": {"WU-A": {"lease_id": "LEASE-A", "epoch": 1}},
        "effective_autonomy_policy": {
            "execution": {
                "stalled_after_minutes": 15,
                "timeouts_seconds_by_step": {"sandbox_implementation": 5400},
            }
        },
    }
    _write_yaml(
        tmp_path / "work-units" / "WU-A.yaml",
        {"id": "WU-A", "status": "in_progress", "updated_at": started},
    )
    _write_yaml(
        tmp_path / "runs" / "execution-attempts" / "ATTEMPT-A.yaml",
        {
            "id": "ATTEMPT-A",
            "run_id": "RUN-WORKING",
            "work_unit_id": "WU-A",
            "worker_lease_id": "LEASE-A",
            "step": "sandbox_implementation",
            "status": "started",
            "started_at": started,
        },
    )

    report = evaluate_run_progress(tmp_path, run, now=now)
    assert report["state"] == "working"
    assert report["active_attempt_ids"] == ["ATTEMPT-A"]
