# Bugbot review rules — Governed AI Dev Team Framework

Bugbot is the third review layer in this framework's pipeline:

```
Developer → QA → Code Reviewer subagent → Agent Review / Bugbot (PR) → human merge
```

It reviews pull requests independently of the `code-reviewer` and `security-reviewer`
subagents defined in `.cursor/agents/`. It does not replace them: the subagents run
inside a Cursor session against the Work Unit and its Context Package, while Bugbot
runs on the PR diff itself, without that session context. Treat a Bugbot finding the
same way as any other review finding — as an event attached to the Work Unit, not as
a silent fix.

This file is read directly by Bugbot on pull requests. It is intentionally plain
language, since Bugbot does not read `.cursor/rules/*.mdc`.

## Evidence and testing

- If a pull request changes `src/**` (or the project's configured source roots) and
  does not touch any test file, flag it as needing tests, per the framework's
  Test Strategy (`.ai-team/constitution/40-test-strategy.yaml`), which requires that
  test presence never substitute for demonstrated behavior.
- If a pull request claims a bug fix but does not add or modify a regression test,
  flag it.
- If a pull request touches authentication, authorization, secrets, permissions,
  payments, or another external trust boundary, and does not include negative-case
  tests, flag it as missing required security coverage.

## Governance and traceability

- If a pull request's description or commits do not reference a Work Unit ID
  (`WU-XXX`), flag it: every product change in this framework must trace back to an
  approved Work Unit in `.ai-team/work-units/`.
- If a pull request modifies files under `.ai-team/constitution/`, flag it as a
  Constitution change requiring explicit human approval (G2), not an ordinary code
  review.
- If a pull request modifies `.ai-team/schemas/*.json` in a way that removes or
  loosens a validation constraint (for example widening an enum, dropping a
  `required` field, or setting `additionalProperties` to `true`), flag it for human
  review, since this framework relies on schemas to make governance mechanically
  enforceable rather than a matter of agent discipline.

## Security-sensitive changes

- If a pull request modifies `.cursor/hooks/guard_shell.py` in a way that removes or
  narrows a blocked-command pattern, flag it as high severity.
- If a pull request modifies `.cursor/permissions.json` to add an entry to
  `terminalAllowlist` or to move an item from `block_instructions` toward
  `allow_instructions`, flag it for explicit human review.
- If a pull request introduces a hardcoded secret, credential, or API key, flag it
  as blocking regardless of environment.
- If a pull request adds a production deployment, database migration, or
  infrastructure-mutating command outside `scripts/` or a documented release path,
  flag it and reference the Git/Release policy
  (`.ai-team/constitution/95-git-release-policy.yaml`).

## Role boundaries

- If a pull request's author is a read-only role per
  `.ai-team/constitution/70-permissions-policy.yaml` (architect, code-reviewer,
  security-reviewer, auditor, product-analyst) and the diff modifies product code
  under the project's source roots rather than review/audit artifacts, flag it —
  read-only roles are not expected to produce implementation diffs.
- If a pull request closes or resolves an Audit Finding
  (`.ai-team/findings/`) without a corresponding remediation Work Unit, flag it: per
  the Audit Strategy, findings and remediation are tracked as first-class objects,
  not resolved implicitly through a code change.

## Severity guidance

Use `high` for anything in "Security-sensitive changes" or missing tests on a
high/critical risk Work Unit. Use `medium` for missing traceability or documentation
drift. Use `low` for style or maintainability observations. Do not block a merge on
`low` findings alone.
