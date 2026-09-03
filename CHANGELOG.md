# Changelog

Les changements notables sont consignés ici. Le format suit Keep a Changelog et les
versions produit suivent Semantic Versioning.

## [Unreleased]

### Added

- Décision **DEC-003** — modèle `framework_source`, increment **INC-0.7.0**, clôture mode nuit, politique G3/G4 et nettoyage doc.
- `scripts/ai-team/sync_source_manifest.py` et validation `framework_source` dans `validate.py`.
- `RecordObservation` et `GenerateRetrospective` sont désormais déclenchés automatiquement par l'orchestrateur (échec/timeout/blocage d'une tentative d'exécution ; clôture de Work Unit ou de Run), en plus de l'invocation manuelle du skill `capture-feedback`.
- `RecordObservation` fusionne les sightings partageant le même `recurrence_key` et le même `work_unit` tant que l'Observation reste non résolue (`occurrence_count`, `last_recorded_at`, preuves).
- `TransitionObservation` : machine à états Observation (`open` → … → `resolved`/`rejected`), `revision` / `expected_revision`, CLI `feedback.py transition`.
- Schéma Feedback Export `1.2` durci : formes `aggregate` / `structured` / `full` pour `observations`, `retrospectives` et `executions`.
- `ExecutionAttempt` porte un `execution_id` de corrélation, `duration_ms`, et un `provider` (modèle, session, requête) ; le Feedback Export inclut un agrégat `executions` (format `1.1`, `export_id`).
- `telemetry.project_ref` : identifiant d'installation aléatoire et indépendant de `project.id`, écrit par l'installateur dans `project-profile.yaml` et utilisé comme référence pseudonyme d'export.
- **ADR-009** — installer/utiliser le framework = acceptation. `telemetry.collection: consented_share` par défaut : export/submit **full** avec `project_id`, sans anonymisation ni `human_authorization` ; `SubmitFeedback` + `feedback.py submit` ; outbox ou `submit_url` ; ingest `learning/inbox/`. Pas de mode `local_only`.
- `SubmitFeedback` best-effort à toute clôture terminale de Run (`completed` et `stopped`) ; exports `failed`/`local_outbox` sous `.ai-team/metrics/outbox/` ; `feedback.py flush-outbox` (et chaque `submit`) retente la transmission.

### Changed

- Documentation produit alignée sur `gov.py` et Installation Record v3 (suppression des références actives à `record_gate.py`).
- **WU-MODE-NUIT-CONFORMITY** clôturée (L4 réel documenté hors scope 0.7.0).
- Le hook Cursor `audit_event.py` minimise et hache les données sensibles avant écriture (commande, sortie, identifiants de session), applique une rotation/rétention configurable (`telemetry.raw_log_retention_days`) et peut être désactivé par projet (`telemetry.collection: disabled`).
- `ExportFeedback` n'exige plus de `human_authorization` : l'usage du framework suffit (ADR-009).
- Feedback Export format `1.2` (`transmission` status).
- `telemetry.collection` : `disabled` | `consented_share` uniquement.### Fixed

- Séparation explicite dépôt framework vs projet installé ; suppression du record dogfood incohérent.
- Intégrité du `RuntimeResult` : le `sha256` de l'artefact `runtime_result` est désormais calculé sur le contenu réellement persisté (il était auparavant calculé avant une réécriture ultérieure du fichier, donc invalide).

## [0.7.0] - Non publiée

- Version actuellement déclarée dans les sources. Aucun tag ni GitHub Release ne doit être
  créé avant clôture de `WU-GIT-GOVERNANCE` et validation du SHA de fusion.

## [0.6.0] - 2026-08-30

- Release de clôture de la migration enregistrée dans l'état projet.
- Anomalie connue : le tag léger historique `v0.6.0` pointe vers un commit dont
  `pyproject.toml` déclare encore `0.4.0`. Le tag est conservé intact ; il ne constitue pas
  un précédent pour les releases futures.

## [0.5.0] - Non publiée

- Incrément planifié et accepté dans le cycle de migration, sans tag Git stable publié.

## [0.4.0] - 2026-08-30

- Dernière lignée monolithique conservée sous `release/0.4.0` et par le tag annoté
  `v0.4.0`.
