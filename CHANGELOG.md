# Changelog

Les changements notables sont consignés ici. Le format suit Keep a Changelog et les
versions produit suivent Semantic Versioning.

## [Unreleased]

### Added

- **Adaptateur Claude Code** (`adapters/claude_code/`,
  `src/governed_ai/adapters/claude_code/`) : les 5 opérations du SPI
  (`describe`, `check_compatibility`, `compile`, `execute`, `collect`)
  implémentées et testées, runtime en mode stub (pas de lancement CLI réel).
  `src/governed_ai/adapters/common/` (nouveau) porte la logique partagée entre
  Adaptateurs (hash d'artefact, garde d'autorité `RecordObservation`/
  `RecordGateDecision`, persistance `RuntimeResult`), migrée hors de
  `adapters/cursor/` sans changement de comportement (Cursor conserve des
  wrappers fins).
  - Parité de rôles/skills avec Cursor : les 17 rôles dotés d'un agent Cursor
    (14 pilotés par le bundle + 3 alignés dynamiquement — `design-system-steward`,
    `product-designer`, `visual-qa` — statiques côté Cursor) et les 25 skills
    sont portés vers `.claude/agents/*.md` et `.claude/skills/`. Le contenu des
    skills est copié à l'identique (frontmatter `name`/`description`/
    `disable-model-invocation` compatible tel quel) hormis 3 références
    littérales à `.cursor/...` corrigées en `.claude/...`. Le champ Cursor
    `readonly` est supprimé au rendu plutôt que propagé.
  - Hooks portés (`.claude/hooks/{audit_event,guard_shell,session_init,backup_push}.py`,
    `run_hook.cmd`) et câblés dans `.claude/settings.json` (`PreToolUse`/
    `PostToolUse` avec `matcher` par outil, `SessionStart`, `SubagentStart`/
    `SubagentStop`, `Stop`) ; `guard_shell.py` bloque les mêmes opérations
    destructrices que Cursor (`git push --force`, `git reset --hard`,
    `rm -rf /`, `kubectl apply/delete/...`, `terraform apply/destroy`,
    branches protégées) via le code de sortie 2 sur `PreToolUse`, le seul
    mécanisme de blocage dur vérifié. Le schéma JSON exact des hooks Claude
    Code (`tool_name`/`tool_input`, `hookSpecificOutput.permissionDecision`)
    est une transcription de bonne foi, **non vérifiée contre une session
    Claude Code réelle** dans cet incrément — testé fonctionnellement en
    subprocess avec ce schéma supposé (13 tests), pas contre le runtime réel.
  - Scoping d'écriture par chemin (`writes.product.paths`) délibérément **non**
    tenté : les chemins sont des symboles (`<work-unit-scope>`) résolus par le
    noyau à l'exécution (`ExecutionRequest.resolved_scope`), pas au moment de
    la compilation — Cursor lui-même reporte ce mécanisme (`project_profile`
    non exploité, "reserved for profile-driven allowlist diffs (later WU)").
    Seules les interdictions statiques invariantes par rôle (secrets,
    `.ai-team/constitution/**`, config d'Adaptateur, commandes destructrices)
    sont portées, à parité stricte avec `.cursor/permissions.json`.
  - Hors périmètre de cet incrément : le lancement CLI réel, le câblage
    installeur, les fixtures golden gelées, les règles `.mdc` (pas
    d'équivalent Claude Code direct retenu) — voir Document 3 §"Grain Claude
    Code résolu partiellement" et Document 0 §2.
- Notifications SMTP non bloquantes avec outbox dédupliquée, reprise sur échec,
  alertes immédiates, digest de fin de Run et routage adapté au profil
  d'autonomie. Transport installé par défaut sur `mail.agenteam.fr:465` en SSL,
  compte complet `support@agenteam.fr`, secret exclusivement hors Git.
- Checkpoints UI formatifs planifiés à G1, non bloquants pour tous les profils
  non supervisés, avec cahier manuel court lié au SHA vérifié.
- `RecordHumanFeedback` / `ReconcileHumanFeedback`, stockage
  `.ai-team/human-feedback/`, affichage `status.py` et analyse d'impact pour
  réinjecter un retour tardif dans les Work Units affectées sans confondre G4.
- Décision **DEC-003** — modèle `framework_source`, increment **INC-0.7.0**, clôture mode nuit, politique G3/G4 et nettoyage doc.
- `scripts/ai-team/sync_source_manifest.py` et validation `framework_source` dans `validate.py`.
- `RecordObservation` et `GenerateRetrospective` sont désormais déclenchés automatiquement par l'orchestrateur (échec/timeout/blocage d'une tentative d'exécution ; clôture de Work Unit ou de Run), en plus de l'invocation manuelle du skill `capture-feedback`.
- `RecordObservation` fusionne les sightings partageant le même `recurrence_key` et le même `work_unit` tant que l'Observation reste non résolue (`occurrence_count`, `last_recorded_at`, preuves).
- `TransitionObservation` : machine à états Observation (`open` → … → `resolved`/`rejected`), `revision` / `expected_revision`, CLI `feedback.py transition`.
- Schéma Feedback Export `1.2` durci : formes `aggregate` / `structured` / `full` pour `observations`, `retrospectives` et `executions`.
- `ExecutionAttempt` porte un `execution_id` de corrélation, `duration_ms`, et un `provider` (modèle, session, requête) ; le Feedback Export inclut un agrégat `executions` (format `1.1`, `export_id`).
- `telemetry.project_ref` : identifiant d'installation aléatoire et indépendant de `project.id`, écrit par l'installateur dans `project-profile.yaml` et utilisé comme référence pseudonyme d'export.
- **ADR-009** — installer/utiliser le framework = acceptation. `telemetry.collection: consented_share` par défaut : export/submit **full** avec `project_id`, sans anonymisation ni `human_authorization` ; destination produit `feedback.agenteam.fr` + HMAC ; outbox sur échec ; ingest fabricant `learning/inbox/`. Pas de mode `local_only`.
- `SubmitFeedback` best-effort à toute clôture terminale de Run (`completed` et `stopped`) ; exports `failed` sous `.ai-team/metrics/outbox/` si réseau/secrets manquants ; `feedback.py flush-outbox` (et chaque `submit`) retente la transmission.

### Changed

- **ADR-007 amendé (2026-09-15)** : le périmètre de cette refonte s'ouvre à l'implémentation de l'**Adaptateur Claude Code**, aux côtés de l'Adaptateur Cursor déjà livré. Codex CLI reste hors périmètre (étude de portabilité du contrat uniquement). Voir Document 0 §2, Document 11 §1 (ADR-007), Document 3 §3 (matrice de traduction revérifiée le 2026-09-15).
- Remontée Feedback ADR-009 : URL produit par défaut `https://feedback.agenteam.fr/v1/feedback-exports` ; enrollment auto à l'install ; submit **HMAC-SHA256-V1** (plus de Bearer `GOVERNED_AI_FEEDBACK_SUBMIT_TOKEN`) ; secrets sous `.ai-team/secrets/feedback-ingest.json`.
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
