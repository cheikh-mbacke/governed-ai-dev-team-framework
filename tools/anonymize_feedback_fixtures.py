"""Anonymize consented Feedback Exports for learning-aggregate regression fixtures.

Reads raw exports from a source directory (default: Downloads/feedback), strips
free-text / identifiers that are not needed for dedup regression, and writes
stable fixtures under tests/fixtures/learning/exports/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / "Downloads" / "feedback"
DEFAULT_OUT = REPO / "tests" / "fixtures" / "learning" / "exports"

_KEEP_OBS = {
    "id",
    "revision",
    "recorded_at",
    "last_recorded_at",
    "category",
    "severity",
    "status",
    "occurrence_count",
    "recurrence_key",
    "phase",
    "work_unit",
    "classification",
    "impact",
    "framework_version",
    "constitution_version",
}
_KEEP_ATTEMPT = {
    "id",
    "revision",
    "status",
    "step",
    "started_at",
    "ended_at",
    "duration_ms",
    "failure_code",
    "failure_scope",
    "work_unit_id",
    "execution_id",
    "run_id",
}


def _hash(value: object, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _anon_observation(row: dict) -> dict:
    out = {k: row[k] for k in _KEEP_OBS if k in row}
    if "id" in out:
        out["id"] = _hash(out["id"], prefix="OBS")
    if "work_unit" in out and out["work_unit"]:
        out["work_unit"] = _hash(out["work_unit"], prefix="WU")
    if "recurrence_key" in out and out["recurrence_key"]:
        # keep structure auto:step:status when present
        key = str(out["recurrence_key"])
        if key.startswith("auto:") and key.count(":") >= 2:
            out["recurrence_key"] = key
        else:
            out["recurrence_key"] = _hash(key, prefix="REC")
    impact = out.get("impact")
    if isinstance(impact, dict):
        cleaned = {
            "blocked_minutes": int(impact.get("blocked_minutes") or 0),
            "rework_required": bool(impact.get("rework_required")),
            "human_intervention": bool(impact.get("human_intervention")),
            "affected_work_units": [
                _hash(item, prefix="WU") for item in (impact.get("affected_work_units") or [])
            ],
        }
        out["impact"] = cleaned
    classification = out.get("classification")
    if isinstance(classification, dict):
        out["classification"] = {
            "origin": classification.get("origin"),
            "confidence": classification.get("confidence"),
        }
    out["symptom"] = "[redacted]"
    out.pop("candidate_improvement", None)
    return out


def _anon_execution(row: dict) -> dict:
    out = {k: row[k] for k in _KEEP_ATTEMPT if k in row}
    for key, prefix in (
        ("id", "ATTEMPT"),
        ("work_unit_id", "WU"),
        ("execution_id", "EXE"),
        ("run_id", "RUN"),
    ):
        if key in out and out[key]:
            out[key] = _hash(out[key], prefix=prefix)
    out["summary"] = "[redacted]"
    return out


def anonymize_document(document: dict, *, export_index: int) -> dict:
    project_seed = document.get("project_ref") or document.get("project_id") or "unknown"
    observations = [
        _anon_observation(row)
        for row in (document.get("observations") or [])
        if isinstance(row, dict)
    ]
    executions = [
        _anon_execution(row)
        for row in (document.get("executions") or [])
        if isinstance(row, dict)
    ]
    summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
    return {
        "format_version": document.get("format_version") or "1.2",
        "export_id": f"EXP-ANON-{export_index:03d}",
        "generated_at": document.get("generated_at") or "2026-09-11T00:00:00+00:00",
        "detail_level": "full",
        "project_ref": _hash(project_seed, prefix="PRJ"),
        "project_id": "anon-fixture",
        "framework_version": document.get("framework_version") or "0.7.0",
        "constitution_version": document.get("constitution_version") or "1.1.0",
        "snapshot_sequence": export_index,
        "summary": {
            "total": int(summary.get("total") or len(observations)),
            "open": int(summary.get("open") or 0),
            "by_category": summary.get("by_category") or {},
            "by_origin": summary.get("by_origin") or {},
            "by_severity": summary.get("by_severity") or {},
        },
        "observations": observations,
        "retrospectives": [],
        "executions": executions,
        "transmission": {
            "status": "skipped",
            "submitted_at": None,
            "destination": None,
            "ack_id": None,
            "error": None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    source: Path = args.source
    out: Path = args.out
    if not source.is_dir():
        raise SystemExit(f"source directory missing: {source}")
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("EXP-ANON-*.json"):
        stale.unlink()
    paths = sorted(source.glob("EXP-*.json"))
    if not paths:
        raise SystemExit(f"no EXP-*.json under {source}")
    unique_ids: set[str] = set()
    total_rows = 0
    for index, path in enumerate(paths, start=1):
        document = json.loads(path.read_text(encoding="utf-8"))
        anon = anonymize_document(document, export_index=index)
        total_rows += len(anon["observations"])
        unique_ids.update(str(row["id"]) for row in anon["observations"] if row.get("id"))
        target = out / f"EXP-ANON-{index:03d}.json"
        target.write_text(json.dumps(anon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(REPO)} ({len(anon['observations'])} observations)")
    print(f"rows={total_rows} unique_observation_ids={len(unique_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
