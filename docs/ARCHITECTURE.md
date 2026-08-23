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

## 4. Review pipeline

Review is layered rather than a single pass, so the diff's author is never its own
final judge:

```text
Developer
    |
    v
QA / Test Agent            (.cursor/agents/qa-test.md)
    |
    v
Code Reviewer subagent     (.cursor/agents/code-reviewer.md, readonly)
    |
    v
Agent Review / Bugbot      (.cursor/BUGBOT.md, runs on the pull request)
    |
    v
Independent Auditor        (.cursor/agents/auditor.md, readonly, when risk requires it)
```

The Code Reviewer subagent evaluates the diff inside a Cursor session, with the
Work Unit and Context Package available. Bugbot evaluates the same change again as
a pull request, without that session's context, using the plain-language rules in
`.cursor/BUGBOT.md`. The two are deliberately redundant: each layer can catch what
the other's vantage point misses. A Bugbot finding is handled the same way as any
other review finding — recorded as an event on the Work Unit, not silently patched.

