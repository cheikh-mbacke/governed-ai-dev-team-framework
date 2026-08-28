"""Helpers for legacy 0.4.x CLI golden characterization tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "legacy-0.4" / "cli"


def normalize_cli_output(text: str) -> str:
    """Strip volatile fragments so golden comparisons stay stable."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    # Absolute Windows paths
    text = re.sub(r"[A-Za-z]:\\(?:[^\\/\n\r\t\"'<>|]+\\)*[^\\/\n\r\t\"'<>|]*", "<PATH>", text)
    # Absolute POSIX paths outside placeholders
    text = re.sub(r"(?<!<)/(?:tmp|var|Users|home)/[^\s\n\"']+", "<PATH>", text)
    # Temp install targets
    text = re.sub(r"<PATH>[/\\]target\b", "<TARGET>", text)
    text = re.sub(r"<PATH>[/\\][^/\n\\]+[/\\]target\b", "<TARGET>", text)
    # Timestamps and generated identifiers
    text = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:+.Z]+", "<TIMESTAMP>", text)
    text = re.sub(r"OBS-[\dTZ_]+(?:-[a-f0-9]+)?", "OBS-<TIMESTAMP>", text)
    text = re.sub(r"OBS-<TIMESTAMP>-[a-f0-9]+", "OBS-<TIMESTAMP>", text)
    text = re.sub(r"RET-[\dTZ_]+(?:-[a-f0-9]+)?", "RET-<TIMESTAMP>", text)
    text = re.sub(
        r"il y a \d+ minute\(s\)",
        "il y a <N> minute(s)",
        text,
    )
    text = re.sub(
        r"\d+ minute\(s\) ago",
        "<N> minute(s) ago",
        text,
    )
    text = re.sub(
        r"gate-[a-z0-9]+-\d{4}-\d{2}-\d{2}-\d{6}\.yaml",
        "gate-<TIMESTAMP>.yaml",
        text,
    )
    return text.rstrip() + "\n" if text else ""


def normalize_preflight_json(stdout: str) -> str:
    payload = json.loads(stdout)
    for section in ("python", "cursor_agent"):
        detail = payload.get(section, {}).get("detail")
        if isinstance(detail, str):
            payload[section]["detail"] = normalize_cli_output(detail).strip()
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def run_cli(args: list[str], cwd: Path | None = None) -> dict[str, object]:
    result = subprocess.run(
        args,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    stdout = result.stdout
    if args[-1:] == ["--json"] and "preflight.py" in " ".join(args):
        stdout = normalize_preflight_json(stdout)
    else:
        stdout = normalize_cli_output(stdout)
    return {
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": normalize_cli_output(result.stderr),
    }


def load_golden(scenario: str) -> dict:
    path = FIXTURES_DIR / f"{scenario}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("platform") and payload["platform"] != sys.platform:
        raise RuntimeError(
            f"Golden fixture {scenario} was captured on {payload['platform']}, "
            f"current platform is {sys.platform}"
        )
    return payload


def install_baseline_target(parent: Path) -> Path:
    target = parent / "golden-target"
    result = subprocess.run(
        [
            sys.executable,
            "tools/install.py",
            "--target",
            str(target),
            "--project-id",
            "golden-baseline",
            "--project-name",
            "Golden Baseline",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr + result.stdout)
    return target
