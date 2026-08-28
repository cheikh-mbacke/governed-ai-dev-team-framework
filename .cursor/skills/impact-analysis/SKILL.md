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
