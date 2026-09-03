# Checklist adoptant

Checklist pour mettre en service un projet avec le framework `0.7.0`.

## 1. Préparation du dépôt

- [ ] Dépôt Git initialisé (recommandé pour updates transactionnelles).
- [ ] Python ≥ 3.10 et dépendances (`requirements.txt`) installés.
- [ ] Structure produit prévue (`docs/product/` ou équivalent) identifiée.

## 2. Installation

- [ ] Installation fraîche exécutée :

  ```bash
  python tools/install.py --target . --project-id <id> --project-name "<nom>"
  ```

- [ ] `.ai-team/installation-record.json` présent (`schema_version: 3`).
- [ ] `.ai-team/project-profile.yaml` complété (identité, commandes, `active_adapter_id`).
- [ ] `.ai-team/sources/source-registry.yaml` renseigné (sources autoritaires).

## 3. Gouvernance initiale

- [ ] Constitution lue (`.ai-team/constitution/`).
- [ ] `AGENTS.md` lu par les contributeurs.
- [ ] Gate **G0** enregistrée (baseline prête).
- [ ] Gate **G1** enregistrée (plan d'exécution / WU approuvés).

## 4. Vérifications post-install

- [ ] `python scripts/ai-team/validate.py` — succès.
- [ ] `python scripts/ai-team/preflight.py` — pas de blocage critique.
- [ ] `.cursor/` présent et cohérent avec le bundle actif (`active-bundle.json`).

## 5. Migration depuis 0.4.x (si applicable)

- [ ] [upgrading.md](upgrading.md) lu.
- [ ] `--dry-run` exécuté et plan revu.
- [ ] Backup `migration-backups/` vérifié après update.
- [ ] Aucun chemin non classable bloquant.

## 6. Exploitation courante

- [ ] Work Units travaillées sur branches isolées `wu/<id>`.
- [ ] Mutations d'état via Command Gateway (`gov.py`) ou wrappers approuvés.
- [ ] Observations enregistrées avec `feedback.py record` quand friction réutilisable.
- [ ] Feedback remonté via `feedback.py submit` (ou clôture de Run) — usage du framework = acceptation.
- [ ] Gates G2–G4 enregistrées avec `--authorization-id` quand requis.

## 7. Avant release candidate

- [ ] Suite Document 14 pertinente exécutée (au minimum distribution + architecture).
- [ ] Revue, audit et acceptation humaine selon risque Work Unit.
- [ ] Limites résiduelles documentées — aucune capacité non prouvée présentée comme garantie.

## 8. Acceptation humaine documentation (WU-P6-DOCS)

- [ ] Guides opérateur relus et jugés suffisants pour install/migrate/rollback sans code source.
- [ ] Écarts signalés via événement structuré si la checklist est incomplète.

## Références

- [operator-guide.md](operator-guide.md)
- [architecture.md](architecture.md)
- [security-model.md](security-model.md)
- [deprecations.md](deprecations.md)
