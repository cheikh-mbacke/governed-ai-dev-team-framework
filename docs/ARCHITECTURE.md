# Architecture

## 1. Control Plane vs Execution Plane

The framework treats the main Cursor Agent running the `orchestrator` Skill as the **Control Plane**. It owns coordination, state transitions, gates, Work Unit readiness, context assembly, staffing decisions, and escalation.

Specialized Cursor subagents form the **Execution Plane**. They implement, test, review, investigate security, prepare releases, and audit according to their mandates.

The Control Plane is not a product authority. It applies human sources and the Engineering Constitution.

## 2. Three kinds of objects

### Human authoritative inputs

- product intent;
- scope / out-of-scope;
- business rules;
- functional and non-functional requirements;
- architecture and contracts;
- constraints;
- acceptance criteria;
- Engineering Constitution;
- recorded human decisions.

### Derived execution model

- Project State;
- Work Units;
- dependency graph;
- risk class;
- context plan;
- staffing allocation;
- required verification.

### Observed results

- repository state;
- runtime observations;
- test evidence;
- reviews;
- defects;
- audit findings;
- release candidates;
- human acceptance results.

A derived or observed object must never silently overwrite a human authoritative source.

## 3. State machine

```text
DRAFT -> READY -> IN_PROGRESS -> VERIFICATION -> REVIEW -> AUDIT
     -> HUMAN_TEST -> DONE

Alternative states:
WAITING_DECISION
BLOCKED
REMEDIATION_REQUIRED
CANCELLED
```

Each transition is allowed only if its policy preconditions are satisfied.
