---
name: integrate-work-units
description: Review cross-Work-Unit coherence before a bounded integration merge.
disable-model-invocation: false
---
# Integrate Work Units

Review shared contracts and dependency ordering. Approve or block the proposed integration merge, then require complete revalidation evidence after every accepted merge.

Return `integration_review`, `merge_disposition` and `revalidation_requirements`. Never merge a protected branch, invent a shared contract or exceed the bounded conflict retry budget.
