---
name: propose-profile
description: Inspect this repository and the docs/product/ folders to propose filled-in values for .ai-team/project-profile.yaml and .ai-team/sources/source-registry.yaml. Never writes either file without explicit human confirmation. Use right after installing the framework, instead of filling those two files by hand.
disable-model-invocation: true
icon: wand
color: green
---
# Propose Profile

This is a **bootstrap convenience**, not a Constitution authority. It never
invents product intent — it only detects technical facts already present in
the repository (what commands exist, what files were dropped where) and asks
a human to confirm before writing anything.

## Part 1 — `.ai-team/project-profile.yaml`

Inspect the repository root for whichever of these are present, and infer
from them:

- `package.json` → `primary_language: javascript` or `typescript` (check for
  `tsconfig.json`), `package_manager` from the lockfile present (`pnpm-lock.yaml`
  → pnpm, `yarn.lock` → yarn, else npm), and propose `commands` from the
  `scripts` block (`build`, `lint`, `test` → `unit_test`, etc.) when present.
- `pyproject.toml` or `requirements.txt` → `primary_language: python`,
  `package_manager` from what's present (`poetry.lock` → poetry, `uv.lock` →
  uv, else pip), and propose commands only for tools actually configured
  (e.g. a `[tool.ruff]` or `[tool.black]` section, a `pytest` dependency).
- `Cargo.toml` → `primary_language: rust`, `package_manager: cargo`,
  `commands.build: "cargo build"`, `commands.unit_test: "cargo test"`.
- `go.mod` → `primary_language: go`, `commands.build: "go build ./..."`,
  `commands.unit_test: "go test ./..."`.
- Common source/test directories present at the root (`src`, `app`, `lib`,
  `test`, `tests`, `spec`) → propose `paths.source_roots` / `paths.test_roots`.

**Never guess a command that isn't backed by something real in the
repository** (a script entry, a config file, a dependency). If nothing
supports a field, leave it as the shipped default (`null` or `unknown`) and
say so explicitly in the proposal — an honest gap is better than a plausible
invention.

`human_authorities` and anything about who has approval authority are never
inferred from the repository; always ask the human directly for these four
names (or leave them `unspecified` if the human doesn't answer yet).

`communication.language` is never inferred either — a repository's code
comments or README language is not a reliable signal of what the human
wants to be addressed in. Ask directly; default to `english` only if the
human has no preference.

## Part 2 — `.ai-team/sources/source-registry.yaml`

List every file under `docs/product/` (including its subfolders, if the
default ones from installation are still there:
`vision-and-scope/`, `users-and-rules/`, `requirements/`,
`acceptance-criteria/`, `architecture-and-constraints/`,
`security-and-compliance/`, `references/`). For each file found, propose a
registry entry:

```yaml
- id: <derived from filename, kebab-case>
  type: human_construction_material
  path: docs/product/<actual path>
  authority: human
  scope: <the subfolder name, or "project" if directly under docs/product/>
  version: "1.0"
  status: active
  owner: product
```

Do not propose an entry for a file you have not actually found on disk, and
do not propose one for a folder's `README.md` stub (those are organizational,
not product material).

## Required output

Present the full proposed content of both files as a diff or block the
human can read in one pass — never write to either file directly. Ask a
single explicit question: which fields to accept as proposed, which to
correct, and which to leave for the human to fill in later. Only write the
files after the human replies with what to keep. State plainly which values
were inferred from a concrete signal (and which signal) versus left
unfilled for lack of one.
