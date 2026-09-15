---
name: match-mandate
description: Propose a typed decision-menu match for deterministic Core validation.
disable-model-invocation: false
---
# Match Mandate

Extract the observed typed trigger without semantic expansion. Select at most one structurally matching decision-menu clause and attach every required evidence reference.

Return `proposed_entry_id`, `trigger` and `evidence`. Never resolve the decision and never assign a default answer to an unmatched fork.
