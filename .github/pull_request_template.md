## Work Unit

- Identifiant : `WU-...`
- SHA candidat :
- Décision ou gate associé, si applicable :

## Résultat observable

Décrire le comportement livré et les limites connues.

## Vérifications

- [ ] `python scripts/ai-team/check_git_policy.py`
- [ ] `python scripts/ai-team/check_release_matrix.py`
- [ ] `python -m ruff check scripts/`
- [ ] `python -m pytest tests/ -q`
- [ ] `python scripts/ai-team/validate.py`
- [ ] `python scripts/ai-team/sync_source_manifest.py --check` (dépôt `framework_source`)
- [ ] Documentation et changelog mis à jour si nécessaire
- [ ] Aucun secret, changement hors périmètre ou finding critique ouvert
- [ ] Les preuves référencent le SHA candidat exact

## Release et rollback

- Impact SemVer : `none / patch / minor / major`
- Migration : `non / oui — lien`
- Rollback ou restauration :
