# Bugbot review rules — framework fabrication workspace

This repository builds the Governed AI Team framework (`repository_kind:
framework_source` in `.fabric/project-profile.yaml`). Bugbot reviews pull requests
for **framework fabrication**: code, tests, installable payload, and distribution —
not an installed client's governance cycle.

There is **no** root `.ai-team/` here. Workflow reference: [`AGENTS.md`](../AGENTS.md).

## Evidence and testing

- If a pull request changes `src/**`, `adapters/**`, or `distribution/**` and
  does not touch any test file, flag it as needing tests per the Test Strategy
  (`distribution/payload/.ai-team/constitution/40-test-strategy.yaml`).
- If a pull request claims a bug fix but does not add or modify a regression test,
  flag it.
- If a pull request touches authentication, authorization, secrets, permissions,
  payments, or another external trust boundary, and does not include negative-case
  tests, flag it as missing required security coverage.

## Traceability and payload changes

- Commits should follow Conventional Commits (`feat:`, `fix:`, `docs:`, etc.) as
  documented in `AGENTS.md` and `VERSIONING.md`.
- If a pull request modifies files under `distribution/payload/.ai-team/constitution/`,
  flag it for explicit human review — this is deliverable product policy, not
  ordinary code.
- If a pull request modifies `distribution/payload/.ai-team/schemas/*.json` in a
  way that removes or loosens a validation constraint (widening an enum, dropping
  a `required` field, or setting `additionalProperties` to `true`), flag it for
  human review.
- If a pull request changes installable payload under `adapters/cursor/templates/`,
  verify that `.fabric/framework-version.json` stays aligned (CI runs
  `sync_source_manifest.py --check`).
- If a pull request adds a root `.ai-team/` directory or client-cycle editor payload
  at the repository root (`.cursor/agents/`, `.cursor/skills/compile-project/`,
  etc.), flag it as high severity — client payload belongs under
  `adapters/cursor/templates/.cursor/` and installable YAML under
  `distribution/payload/.ai-team/`.

## Security-sensitive changes

- If a pull request modifies `.cursor/hooks/guard_shell.py` in a way that removes or
  narrows a blocked-command pattern, flag it as high severity.
- If a pull request modifies `.cursor/permissions.json` to widen shell autonomy,
  flag it for explicit human review.
- If a pull request introduces a hardcoded secret, credential, or API key, flag it
  as blocking regardless of environment.

## Severity guidance

Use `high` for security-sensitive changes or missing tests on critical paths. Use
`medium` for missing traceability or documentation drift. Use `low` for style or
maintainability observations. Do not block a merge on `low` findings alone.
