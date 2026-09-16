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
  - **Câblage installeur** : `tools/install.py --adapter {cursor,claude-code}`
    (défaut `cursor`, inchangé) choisit l'Adaptateur à la première install ;
    `--update` garde toujours l'Adaptateur déjà installé (refuse `--adapter`).
    `active_adapter_id` — jusque-là écrit mais jamais réellement consulté —
    devient un vrai aiguillage : `distribution/installer/adapter_registry.py`
    (nouveau) centralise la correspondance id → répertoire compilé
    (`.cursor`/`.claude`), source relocalisée et fonctions de compilation,
    remplaçant les branches Cursor en dur dans `source_files.py`/`apply.py`.
    `ownership.py`/`scripts/ai-team/validate_ownership.py` classifient
    désormais `.claude/`/`adapters/claude_code/` sous `adapter:claude-code` ;
    `scripts/ai-team/validate.py` n'exige les fichiers `.cursor/*` que si
    l'Adaptateur actif est `cursor` (sinon `.claude/settings.json`) — sans ce
    correctif, un projet installé en `claude-code` échouait `validate.py`
    avec des erreurs sur des fichiers Cursor qui n'ont jamais existé.
    `resolve_bundle_dir`/`minimal_project_profile`/`load_project_profile_yaml`
    déplacés vers `governed_ai.adapters.common` (même pattern d'extraction que
    précédemment). Installation `claude-code` bout en bout vérifiée
    manuellement (`.claude/` matérialisé, `.cursor/` absent,
    `installation-record.json` et `project-profile.yaml` cohérents,
    `validate.py` propre) + 4 tests d'intégration.
  - **Lancement CLI réel** (`adapters/claude_code/runtime/claude_cli.py`) :
    contrairement aux hooks, ce contrat **est vérifié de première main** —
    `claude --help` puis deux appels réels `claude -p --output-format json`
    (un ayant atteint `--max-budget-usd`, un complet) le 2026-09-15, sur
    abonnement Claude Pro (`claude auth status`), pas une clé API. Le schéma
    JSON diffère de celui de Cursor : `usage.input_tokens`/`output_tokens`
    en snake_case (pas `inputTokens`/`outputTokens`), pas de champ
    `request_id` (`uuid` utilisé à la place), `total_cost_usd` au niveau
    racine. `-p` saute nativement le dialogue de confiance workspace (pas
    d'équivalent `--trust` requis) ; `--permission-mode bypassPermissions`
    remplace `--force` de Cursor — l'application reste `.claude/settings.json`
    (`permissions.deny`) et `guard_shell.py` (sortie 2 sur `PreToolUse`), pas
    ce mode. `governed_ai.adapters.common.agent_invocation` (nouveau) porte
    la construction de prompt, le chien de garde kill-switch/Run, l'environ-
    nement assaini et l'arrêt d'arbre de process — extraits de
    `adapters/cursor/runtime/agent_cli.py` sans changement de comportement
    (wrapper fin conservé, `CURSOR_PROJECT_DIR` vs `CLAUDE_PROJECT_DIR` en
    seul paramètre variable). Activé par la même variable d'opt-in
    `GOVERNED_AI_ENABLE_REAL_AGENT_LAUNCH=1` que Cursor ; désactivé par
    défaut, donc gratuit pour la suite de tests (mockée, comme pour Cursor).
  - **Fixtures golden gelées** (`tests/fixtures/claude-code-compile/golden-manifest.json`,
    `tests/generate_claude_code_compile_golden.py`, `adapters/claude_code/compiler/parity.py`) :
    miroir du mécanisme Cursor, sans `shadow_compare` (pas d'arbre `.claude/`
    historique séparé à comparer dans ce dépôt). Vérifié aussi via
    l'installateur (`tools/install.py --adapter claude-code` produit des
    fichiers dont le hash correspond au manifeste gelé).
  - **Règles portées** : les 6 règles Cursor (`.cursor/rules/*.mdc`, toutes
    `alwaysApply: true`) sont fusionnées dans `.claude/CLAUDE.md` plutôt que
    dans un mécanisme `.claude/rules/*.md` non vérifié — CLAUDE.md est le
    seul mécanisme d'injection de contexte confirmé chargé à chaque session.
  - **Outillage préflight minimal** (`adapters/claude_code/runtime/checks.py`) :
    présence du binaire `claude`, validité de `.claude/settings.json`, sondage
    fonctionnel de `guard_shell.py` (code de sortie, pas le format JSON
    `{"permission":...}` de Cursor). Volontairement plus restreint que
    `adapters/cursor/runtime/checks.py` : les concepts `global_allowlist`/
    `execution_surface`/`readonly_sandbox` de Cursor sont propres à son UI
    d'approbation, sans équivalent Claude Code vérifié — non inventés ici.
    **Non câblé** dans `scripts/ai-team/preflight.py` (son alias de mise en
    page installée n'est vérifié que pour Cursor) ; `diagnose.py`,
    `orchestrate.py` et `propose_allowlist.py` restent Cursor uniquement,
    hors périmètre de cet incrément.
  - Hors périmètre restant : le scoping d'écriture par chemin (voir plus
    haut), l'outillage préflight/orchestration au-delà de ce qui précède —
    voir Document 3 §"Grain Claude Code résolu partiellement" et Document 0 §2.
  - **Schéma des hooks vérifié de première main** (2026-09-16, invocations
    réelles `claude -p` avec `.claude/settings.json` et hooks non modifiés) :
    payloads `SessionStart`/`UserPromptSubmit`/`PreToolUse`/`PostToolUse`/`Stop`
    capturés verbatim (fixtures `REAL_PRE_TOOL_USE_BASH_PAYLOAD`/
    `REAL_POST_TOOL_USE_BASH_PAYLOAD` dans `tests/adapters/claude_code/test_hooks.py`).
    Un vrai bug trouvé et corrigé : `audit_event.py` supposait `tool_response`
    string alors que c'est un objet (`{"stdout":...,"stderr":...}`) sur
    `PostToolUse` — la sortie de commande n'était jamais journalisée. Blocage
    dur reconfirmé de bout en bout : `git commit --amend` réellement tenté
    par le modèle a été bloqué par `guard_shell.py` (code de sortie 2), le
    message de refus exact étant relayé tel quel par le modèle. Les
    docstrings des 3 hooks sont mis à jour de "best-effort, non vérifié" à
    "vérifié" avec la preuve citée.
  - **Dispatch réel d'un sous-agent Claude Code depuis un Work Unit gouverné
    vérifié de bout en bout** : `execute_runtime()` non mocké, lancement réel
    activé, arbre `.claude/` livré (non debug) — un sous-agent Claude Code
    réel a écrit un fichier réel, avec les hooks actifs pendant l'exécution ;
    la discipline de gouvernance (`status` reste `"failed"` sans le handoff
    JSON structuré requis, même si la tâche a réellement abouti) s'est
    appliquée sans dérogation, conforme à CG-012/AD-010.
  - **`orchestrate.py`/`diagnose.py` rendus adaptatifs** : l'orchestrateur
    (`scripts/ai-team/orchestrate.py`, seul processus long réellement autonome
    du framework) lit désormais `active_adapter_id` du profil projet et
    instancie `ClaudeCodeAdapter` ou `CursorAdapter` en conséquence (au lieu
    de coder `CursorAdapter` en dur) ; `diagnose.py` lit le même id pour
    choisir le bon fichier de log (`claude-code-events.jsonl` vs
    `cursor-events.jsonl`) et n'affiche le conseil "remontez dans le chat
    Cursor" que pour un projet Cursor — aucun équivalent UI Claude Code n'est
    inventé pour le cas contraire. `propose_allowlist.py` reste Cursor
    uniquement : la génération de motifs de permission pour
    `.claude/settings.json` demanderait une conception nouvelle, pas un
    portage mécanique — délibérément non tenté.
  - **Correctif de portabilité en layout installé** : l'alias d'import
    `adapters.<nom>` vers la copie runtime installée
    (`install_paths.py::_ensure_adapters_cursor_alias`, désormais généralisé
    en `_ensure_adapter_alias`) ne couvrait que `cursor`. Un vrai projet
    installé en `claude-code` (sans paquet `adapters/` racine) aurait échoué
    à l'import dans tout code appelant `ClaudeCodeAdapter` en dehors du
    compilateur — bug latent non exercé jusqu'ici, trouvé en étendant
    `orchestrate.py`, corrigé, et couvert par un nouveau test d'installation
    réelle bout en bout.
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
