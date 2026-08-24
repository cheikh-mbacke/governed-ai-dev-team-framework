# Upgrading an installed project

Use the installer from the **new framework clone**, not a possibly stale copy
inside the target project. Updates are transactional and preserve project-owned
state, but they intentionally replace framework-owned governance files.

## 1. Start from a clean target worktree

Commit or stash every in-progress change before updating. Creating a new branch
does not isolate uncommitted files: they follow the checkout.

```bash
git status --short
# Only when the preceding command reports in-progress work:
git stash push -u -m "wip before framework update"
git switch main
git switch -c chore/framework-update
```

Keep the stash until the framework branch has been reviewed, merged, and the
original work branch has been rebased. Prefer `git stash apply` when restoring
it so a failed or conflicted restoration does not discard the recovery copy.

The updater aborts before writing when the target is dirty or is not a
standalone Git worktree. `--allow-dirty` is an explicit emergency override,
not the normal workflow.

## 2. Preview the complete plan

From the latest framework clone:

```bash
python tools/install.py --target /path/to/project --update --dry-run
```

The plan reports:

- the installed and target framework versions;
- added and replaced framework files;
- project-data migrations;
- dirty paths, when present;
- previously managed files that are now obsolete.

Dry-run uses only the Python standard library and never modifies the target.
Obsolete files are reported but never deleted automatically.

## 3. Apply the update

```bash
python tools/install.py --target /path/to/project --update
```

The updater automatically looks for a validation interpreter in the target's
`.venv` (POSIX or Windows), then falls back to the interpreter running the
installer. It requires PyYAML and jsonschema for the post-update validation.

The update then:

1. snapshots every file it may touch;
2. replaces only changed framework-owned files;
3. applies known idempotent project-data migrations;
4. writes `.ai-team/framework-version.json` with the installed version and
   managed-file manifest;
5. runs `scripts/ai-team/validate.py` in the target;
6. restores all touched files automatically if copying, migration, or
   validation fails.

Migration source files are also retained under
`.ai-team/migration-backups/`, which is ignored by Git.

`--skip-validation` is available only as an explicit emergency override. An
update performed with it is not considered validated.

## 4. Review and test

```bash
git status --short
git diff --check
git diff
python scripts/ai-team/preflight.py
```

Run the target project's own tests, then perform the interactive CLI Allowlist
smoke from `docs/TERMINAL_GUIDE.md`. Under WSL/Linux, also verify the separate
`architect + workspace_readonly` integration path.

## 5. Restoring a stashed Work Unit later

A stash may contain legacy project-data files that were absent during the
framework update. Rebase the clean Work Unit branch **before** restoring the
stash, then run the standalone idempotent migration:

```bash
git switch wu/example
git rebase main
git stash apply stash@{0}
python scripts/ai-team/migrate.py
python scripts/ai-team/migrate.py --apply
python scripts/ai-team/validate.py
```

The first migration command is a dry-run. Drop the stash only after reviewing
the restored work and obtaining a successful validation.

## Ownership boundary

Updated framework-owned paths include `.cursor/`, `.ai-team/constitution/`,
`.ai-team/schemas/`, `.ai-team/templates/`, `scripts/`, `requirements.txt`,
and the category README files under `docs/product/`.

Project-owned profiles, source registries, Work Units, state, decisions,
events, evidence, findings, audits, releases, acceptances, context packages,
logs, migration backups, and authored product documents are preserved. A
known migration may deliberately transform a project-owned file; every such
file is shown in dry-run and backed up before modification.
