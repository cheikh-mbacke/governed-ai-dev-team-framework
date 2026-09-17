---
name: prepare-acceptance
description: Build a human-executable acceptance package for an increment or release, with preconditions, steps, expected outcomes, nominal/error/regression scenarios and evidence capture.
disable-model-invocation: false
icon: beaker
color: yellow
---
# Prepare Human Acceptance

Create an acceptance package under `.ai-team/acceptance/`.

Set `purpose` explicitly:
- `formative_ui_review` for a non-blocking, Work Unit/surface checkpoint;
- `final_acceptance` for formal increment or release acceptance at G4.

For formative UI review, bind the package to `work_unit`, `surface`, and the
exact `code_revision` independently verified by QA. Keep it short: three to
seven scenarios selected for human judgment, not a repetition of every
automated check.

For each scenario include:
- preconditions;
- exact human steps;
- expected observable result;
- nominal/error/regression purpose;
- environment/data requirements;
- evidence the human should capture.

Leave `human_result.status` as `pending` until a human records the result. For
`formative_ui_review`, the response is recorded as a separate HumanFeedback
object and does not itself complete `human_acceptance` or G4.

A failed final-acceptance test creates a DEFECT tied to the increment/release
and affected evidence. Formative feedback is first reconciled against the
current code revision: it may become a defect, UX-adjustment Work Unit, product
decision request, already-satisfied result, or obsolete result. Applicable
remediation returns through development, tests, review and retest.
