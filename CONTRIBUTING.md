# Contribuer

Toute contribution doit respecter `VERSIONING.md`, `AGENTS.md` et la Constitution sous
`.ai-team/constitution/`.

## Parcours minimal

1. Partir d'un `main` à jour et propre.
2. Utiliser une Work Unit approuvée, puis créer `wu/WU-<ID>-<slug>`.
3. Limiter le diff au périmètre de la Work Unit.
4. Ajouter ou adapter les tests et la documentation.
5. Exécuter :

   ```text
   python scripts/ai-team/check_git_policy.py
   python -m ruff check scripts/
   python -m pytest tests/ -q
   python scripts/ai-team/validate.py
   ```

6. Commiter avec `type(WU-ID): description concise`.
7. Ouvrir une pull request en complétant le modèle fourni.
8. Corriger par de nouveaux commits ; ne pas réécrire un SHA déjà évalué.

Une pull request ne doit pas être fusionnée tant qu'un contrôle requis échoue ou qu'un
défaut critique, un finding bloquant ou une décision humaine reste ouvert.

## Changement de version

Une modification de version met à jour simultanément `pyproject.toml`,
`.ai-team/framework-version.json`, `CHANGELOG.md` et le candidat de release. Le tag est
créé seulement après validation du commit de merge sur `main`.

## Signalement de sécurité

Ne publiez pas de secret ni de vulnérabilité exploitable dans une issue publique. Utilisez
le canal privé du mainteneur ou la fonctionnalité GitHub de signalement privé lorsqu'elle
est activée.
