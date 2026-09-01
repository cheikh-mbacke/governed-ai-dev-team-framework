<!-- governed-ai:start -->
# Governed AI Team Instructions

This repository uses the Engineering Constitution under `.ai-team/constitution/`.

## Framework source repository

If `.ai-team/project-profile.yaml` declares `repository_kind: framework_source`,
this repo **builds** the framework — it is **not** an installed client project.

- Edit framework code under `src/`, `adapters/`, `.ai-team/constitution/`, etc.
- Do **not** create `.ai-team/runtime/` or `.ai-team/installation-record.json` here.
- Do **not** edit `tests/fixtures/projects/clean|legacy/` to change product behavior.
- After changing the installable payload:
  `python scripts/ai-team/sync_source_manifest.py` then `python scripts/ai-team/validate.py`
- Never run `python tools/install.py --target .` on this repository.

Work Units and gates here track **framework renovation**, not a post-install client cycle.

Before making product changes:

1. Read `.ai-team/project-profile.yaml` and `.ai-team/state/project-state.yaml`.
2. Work only on an approved, READY Work Unit unless explicitly running `/compile-project`.
3. Do not invent missing product or policy decisions.
4. Treat repository/runtime observations as evidence, not as permission to contradict human authoritative sources.
5. Do not bypass G0-G4 gates.
6. Do not declare DONE without the required evidence, review, audit, and human acceptance status.
7. Use structured events from the communication policy instead of leaving important decisions only in chat.
8. When execution exposes reusable friction, rework, avoidable human intervention,
   or a framework/tool/environment limitation, also record a structured observation
   with `python scripts/ai-team/feedback.py record`. Keep the origin `unknown` until
   evidence supports a stronger classification; the observation does not replace any
   operational BLOCKER, DEFECT, or DECISION_REQUEST required for the current run.
9. Commit coherent Work Unit changes on the isolated working branch before
   QA/review, include the Work Unit ID in the message, and hand off the exact SHA.
   Never stage or commit on a protected branch, and never rewrite history after
   evidence without explicit human authorization and re-verification.
10. Follow `VERSIONING.md` for branch names, commit messages, merge strategy,
    version changes, tags, releases, maintenance branches, and history cutovers.
<!-- governed-ai:end -->
