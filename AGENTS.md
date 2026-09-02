# Governed AI Team — dépôt source du framework

Ce dépôt **fabrique** le framework Governed AI Team. Ce n'est **pas** un projet
client où le framework a été installé et activé.

## Votre workflow ici (fabrication)

Développement logiciel classique :

1. Branche courte depuis `main` (`renov/<slug>`, `fix/<slug>`, etc.).
2. Modifier le code et les tests.
3. Valider : `python -m pytest tests/ -q`, `python scripts/ai-team/validate.py`.
4. Commit Conventional Commits (`feat: …`, `fix: …`, `docs: …`).
5. Pull request vers `main`.

**Ne pas utiliser sur ce dépôt :**

- `/compile-project`, orchestrateur client, gates G0–G4 client ;
- `.ai-team/work-units/`, cycle de preuves client, `feedback.py` ;
- `tools/install.py --target .` (jamais sur ce repo).

## Où éditer quoi

| Zone | Contenu |
|------|---------|
| `src/governed_ai/` | Noyau Python |
| `adapters/` | Adaptateur Cursor et compilateur |
| `distribution/` | Installateur et politique de version |
| `.ai-team/constitution/`, `schemas/`, `contracts/`, `templates/` | Payload installable |
| `adapters/cursor/templates/.cursor/` | **Payload client Cursor** (agents, skills, règles WU/gates) |
| `.cursor/` (racine) | Overlay **fabrication** uniquement — minimal, pas de cycle client |

Pour tester le comportement **installé**, utiliser `tests/fixtures/projects/clean/`
ou `python tools/install.py --target <répertoire-séparé>`.

## Après modification du payload installable

```bash
python scripts/ai-team/sync_source_manifest.py
python scripts/ai-team/validate.py
```

## Règles générales

1. Confirmer `repository_kind: framework_source` dans `.ai-team/project-profile.yaml`.
2. Ne pas inventer d'intention produit ; mettre à jour `docs/product/` si besoin.
3. Ne pas modifier `tests/fixtures/projects/clean|legacy/` pour changer le comportement produit.
4. Suivre `VERSIONING.md` pour branches, versions, tags et releases.

## Projets cibles (après installation)

Sur un projet **installé** (`existing_or_greenfield_project`), le cycle gouverné
client s'applique : Work Units, gates, orchestrateur, preuves. Voir
`docs/operator/adopter-checklist.md` et le `AGENTS.md` généré à l'installation.
