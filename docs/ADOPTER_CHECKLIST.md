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
- [ ] Review `.ai-team/constitution/70-permissions-policy.yaml` and
      `.cursor/permissions.json` (role permissions, blocked command classes).
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
- [ ] CODEOWNERS (or equivalent) for `.ai-team/constitution/` and
      `.cursor/permissions.json`.
- [ ] Production credentials unavailable to ordinary developer agents.

**Before letting the team implement:**
- [ ] Run `/compile-project` and inspect the proposed Work Units, risk and
      staffing.
- [ ] Record G1 approval (`python scripts/ai-team/record_gate.py G1 approved ...`)
      before running `/orchestrator`.
