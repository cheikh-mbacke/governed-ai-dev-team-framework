---
name: design-verification
description: Convert an acceptance oracle into executable verification.
disable-model-invocation: false
---
# Design Verification

Map each acceptance-oracle scenario to a verification level. Design fixtures, thresholds, positive, negative and boundary tests. Identify missing or non-executable acceptance conditions.

Return a `verification_plan`, `coverage_map` and `acceptance_gaps`. Do not approve your own acceptance criteria and do not remove checks required by risk policy.
