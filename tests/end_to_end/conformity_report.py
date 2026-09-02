"""Document 14 §16 conformity report builder for automated L0–L3 runs."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from governed_ai.compat.datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ConformityReport:
    core_version: str = "0.5.0"
    protocol_version: str = "1.0"
    bundle_version: str = "1.0.0"
    adapter: dict[str, str] = field(default_factory=lambda: {"id": "cursor", "version": "0.5.0"})
    environment: dict[str, str] = field(default_factory=dict)
    levels: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_version": self.core_version,
            "protocol_version": self.protocol_version,
            "bundle_version": self.bundle_version,
            "adapter": self.adapter,
            "environment": self.environment,
            "levels": self.levels,
            "failures": self.failures,
            "deviations": self.deviations,
            "generated_at": self.generated_at,
        }


def default_environment() -> dict[str, str]:
    return {
        "os": platform.system().lower(),
        "python": platform.python_version(),
        "tool_version": "simulated-l3-harness",
    }


def l4_availability_note() -> str:
    """Document 14 §3: L4 unavailable must be reported, never counted as passed."""
    return (
        "L4 Cursor real runner not executed in CI — release candidate requires "
        "qualified environment per Document 14 §15."
    )


def run_pytest_subset(paths: list[str], *, repo_root: Path = REPO_ROOT) -> tuple[int, str]:
    command = [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"]
    proc = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=600,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def build_l3_report(*, include_full_suite: bool = False) -> ConformityReport:
    report = ConformityReport(environment=default_environment())
    report.levels["L4"] = "not_run"
    report.deviations.append(l4_availability_note())
    report.levels["L5"] = "manual"

    subsets = {
        "L0": ["tests/architecture/", "tests/contracts/test_bundle.py"],
        "L1": ["tests/core/"],
        "L2": ["tests/distribution/", "tests/adapters/"],
        "L3": ["tests/end_to_end/test_cursor_reference_journey.py"],
    }
    if include_full_suite:
        code, output = run_pytest_subset(["tests/"])
        label = "full_suite"
        if code == 0:
            report.levels[label] = "passed"
        else:
            report.levels[label] = "failed"
            report.failures.append(f"{label}: pytest exit {code}\n{output[-2000:]}")
        return report

    for level, paths in subsets.items():
        code, output = run_pytest_subset(paths)
        report.levels[level] = "passed" if code == 0 else "failed"
        if code != 0:
            report.failures.append(f"{level}: pytest exit {code}\n{output[-1500:]}")

    return report


def write_report(path: Path, report: ConformityReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
