# Governed AI Team — dépôt source du framework

Ce dépôt **fabrique** le framework Governed AI Team (`repository_kind:
framework_source` dans `.fabric/project-profile.yaml`).

Il n'y a **pas** de répertoire `.ai-team/` à la racine — cette structure n'existe
que sur les projets **après installation**.

## Workflow fabrication

1. Branche courte depuis `main` (`renov/<slug>`, `fix/<slug>`, etc.).
2. Modifier le code et les tests.
3. Valider :

   ```bash
   python scripts/ai-team/check_git_policy.py
   python -m ruff check scripts/
   python -m pytest tests/ -q
   python scripts/ai-team/validate.py
   ```

4. Commit Conventional Commits (`feat: …`, `fix: …`, `docs: …`).
5. Pull request vers `main`.

## Où éditer quoi

| Zone | Contenu |
|------|---------|
| `.fabric/` | Identité fabrication (`project-profile.yaml`, manifeste source) |
| `distribution/payload/.ai-team/` | Payload installable (constitution, schémas, contrats, templates) |
| `distribution/payload/seeds/` | Graines fresh-install (profil, état vierge, source-registry) |
| `src/governed_ai/` | Noyau Python |
| `adapters/` | Adaptateur Cursor et compilateur |
| `distribution/installer/` | Installateur et politique de version |
| `adapters/cursor/templates/.cursor/` | Payload client Cursor (agents, skills, règles) |
| `.cursor/` (racine) | Overlay fabrication minimal (hooks, règles courtes) |

## Payload installable

Après modification du payload livré aux projets cibles :

```bash
python scripts/ai-team/sync_source_manifest.py
python scripts/ai-team/validate.py
```

## Comportement installé (référence)

`tests/fixtures/projects/clean/` ou `python tools/install.py --target <répertoire-séparé>`.

## Règles générales

1. Intention produit : `docs/product/` — ne pas inventer.
2. Ne pas modifier `tests/fixtures/projects/clean|legacy/` pour changer le comportement produit.
3. Versions et releases : `VERSIONING.md`.

## Projets cibles (après installation)

Cycle gouverné client : voir [docs/operator/adopter-checklist.md](docs/operator/adopter-checklist.md)
et le `AGENTS.md` généré à l'installation.
