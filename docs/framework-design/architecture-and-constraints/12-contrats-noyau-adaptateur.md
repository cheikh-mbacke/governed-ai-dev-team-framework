# Document 12 — Spécification technique : contrats noyau ↔ Adaptateur

**Statut** : version 1.1 — normative (audit technique indépendant du 28 août 2026 appliqué : `human_authorization` §7.1, exemples Request/Workflow Message §10.1-10.2, note de cohérence identité Adaptateur §3.1). Le protocole initial porte `protocol_version: "1.0"`.

## 1. Principes de compatibilité

- Les versions suivent SemVer.
- Une évolution additive optionnelle est mineure ; supprimer/renommer un champ ou changer sa sémantique est majeur.
- Un Adaptateur déclare un intervalle de protocoles et de bundles supportés.
- Noyau et Adaptateur négocient avant toute exécution. Une incompatibilité retourne `UNSUPPORTED_CONTRACT` sans lancer l’outil.
- Tous les schémas utilisent JSON Schema Draft 2020-12 et `additionalProperties: false`, sauf extensions explicitement namespacées.

## 2. Published Contract Bundle

### 2.1 Manifest

```json
{
  "schema_version": 1,
  "bundle_version": "1.0.0",
  "created_at": "2026-08-28T10:00:00Z",
  "content_hash": "sha256:<hex>",
  "roles": ["roles/backend-developer.json"],
  "procedures": ["procedures/implement-work-unit.json"]
}
```

Le hash est calculé sur une représentation canonique du manifeste sans `content_hash` et de tous les fichiers référencés, triés par chemin. Un bundle publié est immuable.

### 2.2 RoleDefinitionRevision

```json
{
  "role_id": "backend-developer",
  "revision": "1.0.0",
  "mandate": "Implement approved backend Work Units within scope.",
  "writes": {
    "product": {"level": "scoped", "paths": ["<work-unit-scope>"]},
    "authoritative_governance_commands": [],
    "non_authoritative_signal_commands": ["RecordObservation"]
  },
  "capabilities": {
    "repository_read": true,
    "shell": "scoped",
    "network": "deny_by_default",
    "external_tools": []
  },
  "approval_policy": {"mode": "constitution", "cannot_relax": true},
  "procedure_refs": [{"procedure_id": "implement-work-unit", "revision": "1.0.0"}],
  "model_preference": "inherit",
  "isolation": "required_for_concurrent_product_write"
}
```

Les chemins symboliques comme `<work-unit-scope>` sont résolus par le noyau avant transmission. L’Adaptateur ne les interprète pas librement.

### 2.3 ProcedureRevision

```json
{
  "procedure_id": "implement-work-unit",
  "revision": "1.0.0",
  "intent": "Implement the approved Work Unit and return a verifiable handoff.",
  "invocation_mode": "explicit_only",
  "required_inputs": ["work_unit", "context_package", "base_sha"],
  "steps": ["Read inputs", "Implement within scope", "Run required checks"],
  "required_outputs": ["result_sha", "checks", "limitations"],
  "invariants": ["Do not change product authority", "Do not broaden scope"]
}
```

### 2.4 Validation du bundle

La publication échoue si : identifiant/révision dupliqué, référence absente, capacité de Procédure incompatible avec le Rôle, hash incorrect, syntaxe propre à un Adaptateur dans un champ agnostique, ou version de protocole non supportée.

## 3. Adapter Descriptor et SPI

### 3.1 Descriptor

```json
{
  "adapter_id": "cursor",
  "adapter_version": "0.5.0",
  "protocol_versions": ["1.0"],
  "bundle_version_range": ">=1.0.0,<2.0.0",
  "platforms": ["windows", "linux", "macos"],
  "capabilities": {
    "per_role_readonly": true,
    "per_role_product_scope": "partial",
    "mediated_core_commands": true,
    "hooks": true,
    "mcp": true,
    "isolated_worktree": true
  }
}
```

> **Note de cohérence (ajoutée après audit indépendant)** : `adapter_id`/`adapter_version` sont ici des champs plats parce que ce document *est* la description de l'Adaptateur lui-même (auto-description). Dans `ExecutionRequest` (§5) et `RuntimeResult` (§6), l'identité de l'Adaptateur est en revanche portée par un sous-objet imbriqué `"adapter": {"id": ..., "version": ...}`, parce que ces enveloppes décrivent plusieurs entités à la fois (exécution, contrat, poste de travail). Les deux formes sont intentionnellement différentes ; un mappage `adapter_id → adapter.id` et `adapter_version → adapter.version` DOIT être appliqué lors de toute traduction entre Descriptor et enveloppes d'exécution.

### 3.2 Opérations SPI

| Opération | Entrée | Sortie | Effet |
|---|---|---|---|
| `describe()` | — | Adapter Descriptor | Aucun |
| `check_compatibility()` | bundle, rôle, procédure, plateforme | Compatibility Report | Aucun |
| `compile()` | bundle + profil projet | Artifact Manifest | Écrit seulement dans staging |
| `install_artifacts()` | Artifact Manifest | Install Receipt | Mutation gérée par Distribution |
| `execute()` | ExecutionRequest | RuntimeResult | Lance l’outil natif |
| `collect()` | execution_id | RuntimeResult | Lecture/reprise |

Le SPI est une interface Python interne v1, pas une API réseau.

## 4. Compatibility Report

```json
{
  "compatible": false,
  "adapter_id": "cursor",
  "role_id": "auditor",
  "procedure_id": "audit-release",
  "issues": [
    {
      "code": "CAPABILITY_NOT_ENFORCEABLE",
      "path": "writes.non_authoritative_signal_commands",
      "required": "RecordObservation without product write",
      "available": "readonly blocks direct file writes",
      "fallback": "mediated core command"
    }
  ]
}
```

Un fallback n’est appliqué que s’il est déclaré par le contrat et testé. Sinon `compatible=false` bloque l’exécution.

## 5. ExecutionRequest

```json
{
  "protocol_version": "1.0",
  "execution_id": "EXE-<uuid>",
  "correlation_id": "COR-<uuid>",
  "adapter": {"id": "cursor", "version": "0.5.0"},
  "contract": {
    "bundle_version": "1.0.0",
    "bundle_hash": "sha256:<hex>",
    "role_id": "backend-developer",
    "role_revision": "1.0.0",
    "procedure_id": "implement-work-unit",
    "procedure_revision": "1.0.0"
  },
  "project_id": "example-project",
  "work_unit_id": "WU-001",
  "base_sha": "<40-hex>",
  "context_package_ref": "CTX-WU-001",
  "resolved_scope": ["src/api/**"],
  "approvals": [],
  "requested_at": "2026-08-28T10:00:00Z"
}
```

Le `bundle_hash` empêche l’exécution d’un bundle modifié sous la même version. Les références d’entrée sont résolues et validées avant lancement.

## 6. RuntimeResult

```json
{
  "protocol_version": "1.0",
  "execution_id": "EXE-<uuid>",
  "correlation_id": "COR-<uuid>",
  "status": "succeeded",
  "started_at": "2026-08-28T10:00:01Z",
  "finished_at": "2026-08-28T10:05:00Z",
  "adapter": {"id": "cursor", "version": "0.5.0"},
  "contract": {
    "bundle_version": "1.0.0",
    "role_id": "backend-developer",
    "role_revision": "1.0.0",
    "procedure_id": "implement-work-unit",
    "procedure_revision": "1.0.0"
  },
  "workspace": {"base_sha": "<40-hex>", "result_sha": "<40-hex>"},
  "checks": [{"name": "pytest", "status": "passed", "evidence_ref": null}],
  "artifacts": [{"kind": "handoff", "path": ".ai-team/runtime-results/EXE-<uuid>.json", "sha256": "<hex>"}],
  "summary": "Implementation completed.",
  "limitations": [],
  "requested_commands": []
}
```

Valeurs de `status` : `succeeded`, `failed`, `blocked`, `cancelled`, `timed_out`. `summary` et `limitations` sont non autoritaires. `requested_commands` sont des propositions que le Command Gateway revalide intégralement.

## 7. Command Envelope

```json
{
  "protocol_version": "1.0",
  "command_id": "CMD-<uuid>",
  "idempotency_key": "<opaque-unique-key>",
  "correlation_id": "COR-<uuid>",
  "type": "TransitionWorkUnit",
  "issued_at": "2026-08-28T10:06:00Z",
  "actor": {
    "kind": "role",
    "execution_id": "EXE-<uuid>",
    "role_id": "control-plane",
    "bundle_version": "1.0.0",
    "adapter_id": "cursor"
  },
  "target": {"kind": "work_unit", "id": "WU-001", "expected_revision": 3},
  "payload": {"to_status": "verification", "reason": "Implementation handoff validated"}
}
```

`idempotency_key` produit le même reçu pour la même commande. Réutiliser la clé avec un payload différent retourne `IDEMPOTENCY_MISMATCH`.

### 7.1 `human_authorization` (ajouté après audit indépendant)

Toute commande exigeant une autorisation humaine (gates G0-G4, `RecordAcceptance`, `ExportFeedback` avec confidentialité `full`, ou toute commande listée « Autorisation humaine » au §8) porte un champ supplémentaire `human_authorization` dans l'enveloppe :

```json
{
  "human_authorization": {
    "authorization_id": "HAUTH-<uuid>",
    "granted_by": "<human-identifier>",
    "granted_at": "2026-08-28T10:05:00Z",
    "scope": "gate:G3",
    "consumed_at": null
  }
}
```

Invariants :

- `authorization_id` est généré par une action humaine locale explicite (jamais par un Adaptateur ni par un agent) et n'existe qu'une fois avant sa première consommation.
- `scope` lie l'autorisation à exactement une décision (une gate précise, une acceptation précise, un export précis) ; elle ne peut pas être réutilisée pour une autre portée même identique en apparence.
- Dès qu'une commande portant cette autorisation est acceptée, le Command Gateway marque `consumed_at` de façon atomique dans la même transaction que l'effet qu'elle autorise. Toute commande ultérieure référençant le même `authorization_id` retourne `UNAUTHORIZED` (autorisation déjà consommée), pas `IDEMPOTENCY_MISMATCH` : consommer deux fois n'est jamais un doublon légitime, même avec un `idempotency_key` distinct.
- L'absence de `human_authorization` sur une commande qui l'exige retourne `HUMAN_AUTH_REQUIRED` avant toute autre validation.

## 8. Commandes v1

| Commande | Autorité minimale | Effet principal |
|---|---|---|
| `CreateWorkUnit` | Control Plane après compilation autorisée | Crée une Work Unit. |
| `TransitionWorkUnit` | Control Plane + invariants de transition | Change statut/révision. |
| `RegisterEvidence` | Rôle autorisé ou Control Plane | Crée Evidence immuable et référence optionnelle. |
| `RegisterFinding` | Auditeur/Reviewer autorisé | Crée un Finding. |
| `CreateDecisionRequest` | Rôle autorisé | Crée une question humaine. |
| `ResolveDecisionRequest` | Autorisation humaine | Décide/annule la demande. |
| `RecordGateDecision` | Autorisation humaine G0–G4 | Applique état et trace audit dans une transaction. |
| `RegisterReleaseCandidate` | Release | Crée le candidat sans l’approuver. |
| `RecordAcceptance` | Autorisation humaine | Enregistre l’acceptation. |
| `RecordObservation` | Tout Rôle authentifié par son exécution | Crée un signal non autoritaire. |
| `TransitionObservation` | Control Plane ou autorité de feedback | Applique une transition permise. |
| `GenerateRetrospective` | Control Plane | Crée un snapshot Work Unit/projet. |
| `ReviewRetrospective` | Humain/autorité définie | Crée la revue ou change le seul statut selon l’option retenue. |
| `ExportFeedback` | Autorisation humaine spécifique | Exporte avec niveau de confidentialité et destination validés. |

La liste exacte des transitions de Work Unit reste celle du schéma/politique v2 et est testée comme une machine à états fermée.

## 9. Command Receipt et erreurs

```json
{
  "command_id": "CMD-<uuid>",
  "transaction_id": "TX-<uuid>",
  "status": "accepted",
  "affected": [{"kind": "work_unit", "id": "WU-001", "revision": 4}],
  "domain_events": ["EVT-<uuid>"],
  "errors": []
}
```

Codes stables : `INVALID_SCHEMA`, `UNAUTHORIZED`, `HUMAN_AUTH_REQUIRED`, `CONFLICT`, `INVALID_TRANSITION`, `INVARIANT_VIOLATION`, `NOT_FOUND`, `ALREADY_EXISTS`, `IDEMPOTENCY_MISMATCH`, `UNSUPPORTED_CONTRACT`, `CAPABILITY_NOT_ENFORCEABLE`, `TRANSACTION_RECOVERY_REQUIRED`, `INTERNAL_ERROR`.

Les erreurs de validation indiquent un JSON Pointer. Aucune erreur attendue ne produit de traceback sur stdout.

## 10. Domain Event Envelope

```json
{
  "event_id": "EVT-<uuid>",
  "event_type": "WorkUnitTransitioned",
  "event_version": 1,
  "occurred_at": "2026-08-28T10:06:00Z",
  "transaction_id": "TX-<uuid>",
  "correlation_id": "COR-<uuid>",
  "aggregate": {"kind": "work_unit", "id": "WU-001", "revision": 4},
  "data": {"from": "in_progress", "to": "verification"}
}
```

Les événements sont écrits create-exclusive après commit et ne portent pas de `status`. Les Requests et Workflow Messages ont leurs propres schémas.

### 10.1 Request (exemple minimal, ajouté après audit indépendant)

Une Request porte toujours un `status` mutable et une autorité de résolution ; elle n'est jamais create-exclusive comme un Domain Event :

```json
{
  "request_id": "DEC-<uuid>",
  "request_type": "DecisionRequest",
  "status": "pending_human",
  "question": "Which pagination strategy for the public API?",
  "options": ["cursor-based", "offset-based"],
  "raised_by": {"execution_id": "EXE-<uuid>", "role_id": "architect"},
  "correlation_id": "COR-<uuid>",
  "created_at": "2026-08-28T10:06:00Z"
}
```

Une résolution humaine transite par `ResolveDecisionRequest` (§8) et fait passer `status` à `decided` ou `cancelled` ; elle ne réécrit jamais les champs `question`/`options` d'origine.

### 10.2 Workflow Message (exemple minimal, ajouté après audit indépendant)

Un Workflow Message coordonne l'exécution en cours ; il est mutable, n'a pas de portée d'audit et n'entre jamais dans `events/domain/` :

```json
{
  "message_id": "MSG-<uuid>",
  "message_type": "BLOCKER",
  "status": "open",
  "work_unit_id": "WU-001",
  "correlation_id": "COR-<uuid>",
  "summary": "Waiting on architect decision before continuing implementation.",
  "requires_human": true,
  "created_at": "2026-08-28T10:06:00Z",
  "resolved_at": null
}
```

`message_type` reprend les valeurs opérationnelles héritées de `StructuredEvent` qui ne sont ni un fait passé ni une commande (`STATUS`, `CONTEXT_REQUEST`, `CLARIFICATION_REQUEST`, `BLOCKER`, `REVIEW_REQUEST`, `SKILL_REQUEST`, `HANDOFF`) ; `DECISION_REQUEST`, `CONTRACT_CHANGE` et `DEFECT` migrent respectivement vers Request (§10.1), Domain Event ou Finding selon leur nature réelle.

## 11. CLI et codes de sortie

| Code | Sens |
|---:|---|
| 0 | Commande acceptée ou requête réussie. |
| 2 | Entrée/CLI invalide. |
| 3 | Schéma ou invariant invalide. |
| 4 | Non autorisé ou autorisation humaine requise. |
| 5 | Conflit de révision/idempotence. |
| 6 | Contrat ou capacité non supporté. |
| 7 | Récupération transactionnelle requise. |
| 10 | Erreur interne inattendue. |

stdout contient uniquement le JSON de résultat ; diagnostics humains et traces vont sur stderr.

## 12. Limites

- Les schémas JSON complets seront les artefacts d’implémentation de cette spécification ; les exemples ci-dessus ne les remplacent pas.
- L’authentification forte d’un humain distant est hors périmètre ; v1 utilise une autorisation locale explicite.
- Le transport est fichier/stdin + processus local, pas HTTP.
