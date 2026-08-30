---
name: prepare-acceptance
description: Build a human-executable acceptance package for an increment or release, with preconditions, steps, expected outcomes, nominal/error/regression scenarios and evidence capture.
disable-model-invocation: false
icon: beaker
color: yellow
---
# Prepare Human Acceptance

Create an acceptance package under `.ai-team/acceptance/`.

For each scenario include:
- preconditions;
- exact human steps;
- expected observable result;
- nominal/error/regression purpose;
- environment/data requirements;
- evidence the human should capture.

Leave `human_result.status` as `pending` until a human records the result.

A failed human test creates a DEFECT tied to the increment/release and affected evidence. Remediation returns through development, tests, review and retest.
