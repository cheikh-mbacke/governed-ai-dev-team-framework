# Learning fixtures (anonymized Feedback Exports)

**Dedicated tree** — these files live only under `tests/fixtures/learning/`.
They must **never** be copied into `tests/fixtures/projects/clean/` or
`tests/fixtures/projects/legacy/` (those are install witnesses, not feedback
evidence).

## Purpose

Regression evidence for cumulative Feedback Export **deduplication**: the same
observation identity appears across successive snapshots; the aggregator must
keep one row per `(project_ref, observation id)` using the latest
`revision` / `last_recorded_at`.

## Regenerate

```bash
python tools/anonymize_feedback_fixtures.py --source <path-to-raw-EXP-exports>
```

Default output: `tests/fixtures/learning/exports/EXP-ANON-*.json` plus
`tests/fixtures/learning/MANIFEST.json`.

## Preserved (relations)

| Field | Why |
|---|---|
| Hashed `id` / `observation` identity | Stable across snapshots → duplicate detection |
| `revision`, `recorded_at`, `last_recorded_at`, `occurrence_count` | Latest-wins ordering |
| `snapshot_sequence` | Monotonic export order |
| `recurrence_key` (`auto:step:status` kept) | Recurrence buckets |
| Attempt `id`/`step`/`status`/`failure_*` (hashed ids) | Attempt-side dedup / taxonomy |

## Removed (sensitive / noise)

- Raw `project_id` / `project_ref` (replaced by stable `PRJ-…` hash + `anon-fixture`)
- Provider payloads, model names, API material
- Local paths (`C:\…`, `/home/…`, worktree paths)
- Transcripts, stdout/stderr, free-text `symptom` / improvements
- Evidence refs that could leak absolute paths

Baseline counts are recorded in `MANIFEST.json` and asserted by
`tests/test_learning_anon_fixtures.py`.
