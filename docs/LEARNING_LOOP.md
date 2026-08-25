# Framework learning loop

The learning loop keeps three distinct layers:

1. an operational **event** (`BLOCKER`, `DEFECT`, `DECISION_REQUEST`, ...)
   drives the current execution;
2. an **observation** captures friction that may generalize into a framework
   improvement;
3. a **retrospective** aggregates recorded objects without inventing causality.

## Record friction

```bash
python scripts/ai-team/feedback.py record \
  --category context \
  --severity medium \
  --origin unknown \
  --confidence low \
  --work-unit WU-014 \
  --symptom "The shared contract was missing from the Context Package" \
  --blocked-minutes 35 \
  --rework-required \
  --human-intervention \
  --evidence-ref EVT-042 \
  --recurrence-key missing-shared-contract-context
```

Keep `origin: unknown` until evidence distinguishes framework, project,
environment, external-service, and human-process causes. An observation never
replaces the operational `BLOCKER` or `DEFECT` required by the runtime.

## Generate retrospectives

```bash
python scripts/ai-team/feedback.py retrospective --work-unit WU-014
python scripts/ai-team/feedback.py retrospective --project
```

Snapshots under `.ai-team/retrospectives/` aggregate traceable counts for
observations, events, decisions, findings, acceptance, blocked time, rework, and
human intervention.

## Export for cross-project analysis

```bash
# Recommended: structured fields without project identity or free text
python scripts/ai-team/feedback.py export

# Counts only
python scripts/ai-team/feedback.py export --detail-level aggregate

# Complete content: review before sharing
python scripts/ai-team/feedback.py export --detail-level full
```

Exports are written under `.ai-team/metrics/`. The default `structured` level
uses a stable project hash, removes free-text symptoms and improvement proposals,
and hashes recurrence keys. `full` exports may contain project-sensitive data.

`validate.py` checks observations, retrospectives, and their references.
`status.py` reports unresolved observations by category. Repeated correlation is
not proof of causality; inspect evidence before changing the Constitution or
framework defaults.
