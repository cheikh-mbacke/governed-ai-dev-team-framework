# Contribuer

Toute contribution doit respecter `VERSIONING.md`, `AGENTS.md` et la Constitution sous
`.ai-team/constitution/`.

## Dépôt source du framework (`repository_kind: framework_source`)

Ce dépôt **fabrique** le framework. Ce n'est **pas** un projet client où le framework
a été installé et activé.

- Éditer le code sous `src/`, `adapters/`, `distribution/` et le payload installable
  (`.ai-team/constitution/`, schémas, contrats, templates, `.cursor/` à la racine).
- Ne pas lancer `/compile-project`, l'orchestrateur client, les gates G0–G4 client, ni
  `scripts/ai-team/feedback.py` **sur ce dépôt**.
- Ne pas remplir `.ai-team/work-units/`, `events/`, `evidence/`, etc. — l'historique de
  refonte vit dans **git**, pas dans l'état runtime client.
- Après modification du payload installable :
  `python scripts/ai-team/sync_source_manifest.py` puis `python scripts/ai-team/validate.py`
- Branche courte depuis `main` (ex. `renov/<slug>` ou `fix/<slug>`), PR, tests CI.

Parcours minimal :

1. Partir d'un `main` à jour et propre.
2. Créer une branche courte ; limiter le diff au changement visé.
3. Ajouter ou adapter les tests et la documentation.
4. Exécuter :

   ```text
   python scripts/ai-team/check_git_policy.py
   python -m ruff check scripts/
   python -m pytest tests/ -q
   python scripts/ai-team/validate.py
   ```

5. Commiter avec un message concis (`fix: …`, `feat: …`, `docs: …`).
6. Ouvrir une pull request en complétant le modèle fourni.

## Projet client installé (`existing_or_greenfield_project`)

Sur un **projet cible** après `tools/install.py`, le cycle gouverné client s'applique :

1. Work Unit approuvée, branche `wu/WU-<ID>-<slug>`.
2. Implémentation, preuves, revue, audit selon la Constitution.
3. Commit `type(WU-ID): description concise`.

Voir `AGENTS.md` sur le projet installé et la checklist adoptant.

## Changement de version

Une modification de version met à jour simultanément `pyproject.toml`,
`.ai-team/framework-version.json`, `CHANGELOG.md` et le candidat de release. Le tag est
créé seulement après validation du commit de merge sur `main`.

## Signalement de sécurité

Ne publiez pas de secret ni de vulnérabilité exploitable dans une issue publique. Utilisez
le canal privé du mainteneur ou la fonctionnalité GitHub de signalement privé lorsqu'elle
est activée.
