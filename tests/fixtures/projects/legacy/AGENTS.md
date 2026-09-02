<!-- governed-ai:start -->
# Governed AI Team Instructions

This repository uses the Engineering Constitution under `.ai-team/constitution/`.

## Framework source repository

If `.ai-team/project-profile.yaml` declares `repository_kind: framework_source`,
this repo **builds** the framework — it is **not** an installed client project.

- Edit framework code under `src/`, `adapters/`, `distribution/`, and the
  installable payload under `.ai-team/constitution/`, `.ai-team/schemas/`,
  `.ai-team/contracts/`, `.ai-team/templates/`.
- `.ai-team/state/project-state.yaml` is a **virgin template** (`phase:
  not_compiled`, empty `work_units`). It is not an active client runtime.
- Do **not** run `/compile-project`, client gate cycles, or Work Unit orchestration
  on this repository.
- Do **not** create `.ai-team/runtime/` or `.ai-team/installation-record.json` here.
- Do **not** run `scripts/ai-team/feedback.py` record, retrospective, or export here.
- Do **not** edit `tests/fixtures/projects/clean|legacy/` to change product behavior.
- To test installed behavior, use `tests/fixtures/projects/clean/` or
  `python tools/install.py --target <separate-dir>` — never `--target .` on this repo.
- After changing the installable payload:
  `python scripts/ai-team/sync_source_manifest.py` then `python scripts/ai-team/validate.py`

Before making framework code changes:

1. Read `.ai-team/project-profile.yaml` to confirm `repository_kind:
   framework_source`.
2. Do not invent missing product or policy decisions; update human product sources
   under `docs/product/` when intent changes.
3. Treat repository/runtime observations as evidence, not as permission to
   contradict human authoritative sources.
4. When execution exposes reusable friction on an **installed target project**,
   record it there with `python scripts/ai-team/feedback.py record` — not in this
   source repository.
5. Follow `VERSIONING.md` for branch names, commit messages, merge strategy,
   version changes, tags, releases, maintenance branches, and history cutovers.
<!-- governed-ai:end -->
