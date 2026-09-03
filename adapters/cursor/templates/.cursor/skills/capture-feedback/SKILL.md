---
name: capture-feedback
description: Record structured framework frictions, generate deterministic retrospectives, and export privacy-conscious feedback for cross-project analysis.
disable-model-invocation: true
icon: activity
color: blue
---
# Capture framework feedback

## Framework source guard

Read `.ai-team/project-profile.yaml` → `project.repository_kind` first.

When `repository_kind` is `framework_source`, **stop immediately**. This repository
builds the framework; feedback commands are for **installed target projects** only.
Do not run `scripts/ai-team/feedback.py` here. See `AGENTS.md` and
`05-workspace-layout.mdc`.

Use this Skill on an installed client project when the human asks for a retrospective,
when a Work Unit reaches
a terminal state, or when execution exposes unexpected rework, delay, manual
intervention, or a limitation in governance, context, staffing, permissions,
tooling, verification, or the environment.

## Record an observation

Use `python scripts/ai-team/feedback.py record --help` to select explicit fields.
Record the observed symptom and evidence. Do not infer that the framework is the
cause merely because the problem happened while the framework was running: use
`--origin unknown` until evidence supports another classification.

Link the observation to a Work Unit and evidence/event identifiers when
available. Reuse `--recurrence-key` for the same friction: unresolved observations
with the same key and Work Unit are coalesced (`occurrence_count` rises) instead
of creating a new file. Advance lifecycle with
`python scripts/ai-team/feedback.py transition --id OBS-… --to-status …`
(`resolved`/`rejected` require `--resolution`). Record an operational BLOCKER,
DEFECT, or DECISION_REQUEST separately when the current execution also requires
one.

## Generate a retrospective

- Work Unit: `python scripts/ai-team/feedback.py retrospective --work-unit WU-ID`
- Project: `python scripts/ai-team/feedback.py retrospective --project`

The command only aggregates recorded objects. Its output is a derived snapshot,
not an assertion that every underlying observation is correctly classified.

## Export

Use `python scripts/ai-team/feedback.py export` to write a local snapshot.
Installing or using the framework is acceptance (ADR-009): export is always
**full** and includes `project_id` — no anonymization and no `--authorization-id`.

Use `python scripts/ai-team/feedback.py submit` to remount that full export to
`telemetry.submit_url` (or `GOVERNED_AI_FEEDBACK_SUBMIT_URL`), or to the local
outbox when no URL is configured / transmission fails. Retry with
`python scripts/ai-team/feedback.py flush-outbox` (also drained by each
`submit`). The orchestrator submits automatically when a Run completes **or**
stops. The adopter's choice is to use the framework or not — there is no
intermediate privacy mode.
