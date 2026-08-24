# Adopter checklist

The Quickstart in the main `README.md` is the fast path. Use this checklist
before running the framework on a real project, especially before a
production-facing release.

**Must fill — genuinely empty by design:**
- [ ] Install the framework into the repository (`tools/install.py`).
- [ ] Fill `.ai-team/project-profile.yaml`: project identity, source/test/config
      roots, setup/build/lint/typecheck/test commands, human authorities for
      product, Constitution, production release and final acceptance.
- [ ] Add product material under `docs/product/`.
- [ ] Register every authoritative source in `.ai-team/sources/source-registry.yaml`.
- [ ] Run `python scripts/ai-team/validate.py` and resolve every warning.

**Should review — shipped as working defaults, not placeholders:**
- [ ] Review `.ai-team/constitution/60-staffing-policy.yaml` and
      `15-risk-strategy.yaml` (WIP limits, activation rules); adjust only if
      your project's risk profile differs from the reference profile.
- [ ] Review `.ai-team/constitution/70-permissions-policy.yaml` and both
      `.cursor/permissions.json` and `.cursor/cli.json` (role permissions,
      UI/CLI allowlists and blocked command classes).
- [ ] Run `python scripts/ai-team/preflight.py` (or the available Python 3
      command) before any CLI smoke test. Require `PASS` for `hooks_config`,
      `guard_hook`, and `project_cli`. The portable runner selects the local
      Python command; do not make a machine-specific edit to `.cursor/hooks.json`.
      A broken fail-closed hook blocks every shell command and is not an
      Allowlist result.
- [ ] If using Cursor CLI, complete the subagent Allowlist smoke test in
      `docs/TERMINAL_GUIDE.md` section 5 **from the `agent` CLI terminal**
      (not the UI Agent chat), using `auth-smoke` for deny → allow-once.
      Keep `architect` readonly; use WSL/Linux if you also need to validate
      `workspace_readonly`. Do this with one active writer before increasing
      WIP limits.
- [ ] Review `.cursor/BUGBOT.md` if your stack needs stack-specific review
      rules in addition to the governance rules already there.
- [ ] If the project has a UI: fetch `webapp-testing`'s scripts/examples
      (`npx skills add https://github.com/anthropics/skills --skill webapp-testing`)
      and install Playwright (`pip install playwright && playwright install chromium`).
      Without this, `.ai-team/constitution/35-ui-ux-strategy.yaml` sections 6
      and 7 can't be verified with real evidence — see
      `.cursor/skills/webapp-testing/SKILL.md`.

**Must configure outside Cursor — no framework file can enforce these:**
- [ ] Protected branch / required CI checks.
- [ ] CODEOWNERS (or equivalent) for `.ai-team/constitution/`,
      `.cursor/permissions.json`, `.cursor/cli.json` and `.cursor/hooks.json`.
- [ ] Production credentials unavailable to ordinary developer agents.

**Before letting the team implement:**
- [ ] Run `/compile-project` and inspect the proposed Work Units, risk and
      staffing.
- [ ] Record G1 approval (`python scripts/ai-team/record_gate.py G1 approved ...`)
      before running `/orchestrator`.
