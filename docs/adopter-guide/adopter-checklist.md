# Checklist adoptant

Checklist pour mettre en service un projet avec le framework `0.7.0`.

## 0. Assessment d’adoption (avant toute écriture)

La gouvernance est **exclusive** : pas d’adoption à moitié. Inventaire des conflits **avant** l’install — voir [adoption-assessment.md](adoption-assessment.md) (Documents 19–20).

- [ ] `python tools/assess.py --target . --json --report-file assessment.json` (lecture seule).
- [ ] Constats `blocking` résolus via `--resolutions` (`eliminate` / `remap` / `waive` tracé) — sinon **ne pas installer** (`no_go`).
- [ ] Décision d’adoption humaine enregistrée (qui, date, lien vers le rapport).
- [ ] Install avec `--assessment-report assessment.json` (pas de mode hybride).
- [ ] Équipe alignée : pas d’autorité agent/process concurrente laissée non résolue.

## 1. Préparation du dépôt

- [ ] Dépôt Git initialisé (recommandé pour updates transactionnelles).
- [ ] Python ≥ 3.10 et dépendances (`requirements.txt`) installés.
- [ ] Structure produit prévue (`docs/product/` ou équivalent) identifiée.

## 2. Installation

- [ ] Installation fraîche exécutée :

  ```bash
  python tools/install.py --target . --project-id <id> --project-name "<nom>" \
    --assessment-report assessment.json
  ```

- [ ] `.ai-team/installation-record.json` présent (`schema_version: 3`).
- [ ] `.ai-team/project-profile.yaml` complété (identité, commandes, `active_adapter_id`).
- [ ] `.ai-team/sources/source-registry.yaml` renseigné (sources autoritaires).

## 2bis. Baseline avant première compile (surtout brownfield)

Ne pas lancer `/compile-project` tant que cette section n’est pas tenue. Le dépôt existant est une **réalité observée**, pas l’intention produit.

- [ ] Matière humaine autoritaire suffisante pour le premier périmètre (`docs/product/` ou sources enregistrées) — Definition of Ready.
- [ ] Inventaire as-built écrit : écarts de conformité, surfaces hors-scope, nettoyage / remediation prévus.
- [ ] Warnings `baseline.*` du rapport d’assessment traités (`remap` / `waive` tracé) ou reportés explicitement hors du premier périmètre.
- [ ] Aucune règle produit inventée « parce que le code le fait déjà ».

## 3. Gouvernance initiale

- [ ] Constitution lue (`.ai-team/constitution/`).
- [ ] `AGENTS.md` lu par les contributeurs.
- [ ] Gate **G0** enregistrée (baseline prête, y compris inventaire as-built si brownfield) — distincte de l’assessment pré-install.
- [ ] Gate **G1** enregistrée (plan d'exécution / WU approuvés, y compris WU de cleanup/alignement si inventoriés).

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
- [ ] Gates G2–G4 enregistrées avec `--authorization-id` quand requis.

## 7. Avant release candidate

- [ ] Suite Document 14 pertinente exécutée (au minimum distribution + architecture).
- [ ] Revue, audit et acceptation humaine selon risque Work Unit.
- [ ] Limites résiduelles documentées — aucune capacité non prouvée présentée comme garantie.

## 8. Acceptation humaine documentation (WU-P6-DOCS)

- [ ] Guides opérateur relus et jugés suffisants pour install/migrate/rollback sans code source.
- [ ] Écarts signalés via événement structuré si la checklist est incomplète.

## Références

- [adoption-assessment.md](adoption-assessment.md)
- [operator-guide.md](operator-guide.md)
- [architecture.md](architecture.md)
- [security-model.md](security-model.md)
- [deprecations.md](deprecations.md)
