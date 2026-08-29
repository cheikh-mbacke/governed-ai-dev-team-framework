"""Meta tests for Document 14 §16 conformity report structure."""

from __future__ import annotations

import json
from pathlib import Path

from tests.end_to_end.conformity_report import ConformityReport, default_environment, write_report


def test_conformity_report_schema_fields(tmp_path: Path) -> None:
    report = ConformityReport(environment=default_environment())
    report.levels = {"L0": "passed", "L1": "passed", "L2": "passed", "L3": "passed", "L4": "not_run", "L5": "manual"}
    report.deviations.append("L4 not executed")

    payload = report.to_dict()
    for key in (
        "core_version",
        "protocol_version",
        "bundle_version",
        "adapter",
        "environment",
        "levels",
        "failures",
        "deviations",
        "generated_at",
    ):
        assert key in payload

    out = tmp_path / "conformity-report.json"
    write_report(out, report)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["levels"]["L4"] == "not_run"
    assert loaded["adapter"]["id"] == "cursor"
