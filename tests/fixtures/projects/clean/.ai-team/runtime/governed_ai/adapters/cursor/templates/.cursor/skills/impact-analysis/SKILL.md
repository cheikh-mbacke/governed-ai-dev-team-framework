---
name: impact-analysis
description: Analyze the impact of changed human sources, shared contracts, architecture or policy on existing Work Units and derived project state.
disable-model-invocation: false
icon: git-branch
color: orange
---
# Impact Analysis

Use when:
- an authoritative human source changes;
- asynchronous human feedback is received against an earlier UI revision;
- a shared contract changes;
- a structural migration is proposed;
- a Constitution version changes between cycles.

Identify affected Work Units and classify each as:
- unaffected;
- needs_context_refresh;
- needs_reverification;
- invalidated_needs_recompile;
- blocked_pending_decision.

Never silently preserve a derived plan that contradicts a changed authoritative source.

## Asynchronous human UI feedback

For every HumanFeedback in `pending_reconciliation`:

1. Compare `observed_revision.commit_sha` with the current code revision and
   inspect changes made since the human-tested revision.
2. Classify the feedback as defect, UX adjustment, product-intent change,
   already satisfied, or obsolete.
3. Identify the producing Work Unit and all dependent Work Units. Continue
   unrelated nodes; an open checkpoint or pending feedback is never a global
   stop condition.
4. Identify evidence made stale by the required change. Evidence remains an
   immutable historical fact; record invalidation in the reconciliation rather
   than rewriting old evidence.
5. Before `ReconcileHumanFeedback`, create every required remediation Work Unit
   or Decision Request through the Command Gateway. Reuse an in-flight Work Unit
   only when its legal state transition and scope permit it; never reopen a
   terminal Work Unit silently.
6. Record the reconciliation and action references with
   `ReconcileHumanFeedback` before the next affected dispatch.

If a product-intent choice is missing, create a Decision Request and block only
its dependent subgraph. The absence of a human response to the original visual
checkpoint is not such a decision and must not block unattended execution.

Do not invent product decisions to resolve conflicts. Surface blocked pending
decision cases explicitly instead of assuming resolution.
