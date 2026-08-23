---
name: compile-project
description: Compile authoritative human product material and the Engineering Constitution into a readiness report, Project State, dependency graph, Work Units, risk, context plan and initial staffing. Must run before first runtime activation or after material source changes.
disable-model-invocation: true
icon: book-open
color: blue
---
# Compile Project

This is a **planning-only** operation. Do not implement product code.

## Required inputs

Read:
- `.ai-team/constitution/`
- `.ai-team/project-profile.yaml`
- `.ai-team/sources/source-registry.yaml`
- registered authoritative product sources
- repository only as observed reality when relevant

## Procedure

1. Run Definition of Ready against the requested scope.
2. If blocking ambiguity exists, emit G0 issues and stop the affected scope.
3. Build capabilities/features without inventing a new product structure.
4. Decompose into small, observable, testable Work Units.
5. Build explicit dependencies and identify the critical path.
6. Assign risk class from policy and record reasons.
7. Determine required verification from behavior + risk.
8. Build a Context Package plan for each Work Unit.
9. Propose staffing from staffing policy.
10. Update `.ai-team/state/project-state.yaml` and `.ai-team/work-units/`.
11. Produce a concise execution-plan summary.
12. Set phase to `awaiting_g1_approval`.
13. STOP. Do not activate developers until a human records G1 approval.

## Required outputs

- readiness summary;
- generated/updated Work Units;
- dependency graph representation in Project State;
- risk and verification assignments;
- staffing proposal;
- unresolved decisions;
- G1 decision package.
