# Document 14 — Spécification technique : tests de conformité

**Statut** : version 1.1 — normative (audit technique indépendant du 28 août 2026 appliqué : SM-001/SM-002 §6, TX-009 §7, MIG-001/MIG-002 §10bis). Une version ne peut être déclarée conforme si un test obligatoire échoue ou est ignoré sans dérogation humaine documentée.

## 1. Objectifs

La suite prouve séparément :

1. les invariants du noyau ;
2. la sûreté de la persistance ;
3. la conformité d’un Adaptateur au protocole ;
4. la parité Cursor ;
5. la préservation des données par Distribution ;
6. la portabilité des formats indépendamment de l’outil.

Elle ne prétend pas certifier la qualité du modèle IA ni la sécurité générale de Cursor, Claude Code ou Codex.

## 2. Organisation

```text
tests/
  fixtures/
    legacy-0.4/
    bundles/
    projects/
    runtime-results/
  core/
    test_commands.py
    test_state_machines.py
    test_authority.py
    test_transactions.py
    test_recovery.py
    test_events.py
  contracts/
    test_bundle.py
    test_protocol_schemas.py
  adapters/
    conformance_suite.py
    cursor/
  distribution/
    test_install.py
    test_update.py
    test_migrate_v1_v2.py
    test_rollback.py
  architecture/
    test_dependencies.py
    test_named_tool_leaks.py
  end_to_end/
    test_cursor_reference_journey.py
```

Chaque test utilise un répertoire temporaire isolé ; aucun test ne modifie le dépôt source ou le profil utilisateur.

## 3. Niveaux et fréquence

| Niveau | Contenu | CI pull request | CI release |
|---|---|---:|---:|
| L0 | Schémas, imports, formatage, tests unitaires purs | Oui | Oui |
| L1 | Commandes et repositories sur fichiers temporaires | Oui | Oui |
| L2 | Adaptateur compilé et Distribution | Oui | Oui |
| L3 | Cursor simulé/fake runtime déterministe | Oui | Oui |
| L4 | Cursor réel, parcours contrôlé | Selon disponibilité, rapporté | Obligatoire sur environnement qualifié |
| L5 | Tests manuels gates/acceptation/OS | Non | Checklist signée |

Un test L4 indisponible ne doit jamais être compté comme réussi ; la release reste candidate jusqu’à exécution.

## 4. Conformité des contrats

| ID | Test obligatoire | Résultat attendu |
|---|---|---|
| CT-001 | Bundle minimal valide | Accepté, hash reproductible. |
| CT-002 | RoleId dupliqué | Rejet `INVALID_SCHEMA`/invariant. |
| CT-003 | Procédure référencée absente | Rejet avant publication. |
| CT-004 | Bundle modifié après calcul du hash | Rejet. |
| CT-005 | Syntaxe `.cursor` dans un champ agnostique réservé | Rejet par lint de frontière. |
| CT-006 | Champ obligatoire inconnu/supprimé | Rejet selon version majeure. |
| CT-007 | Extension namespacée autorisée | Préservée sans modifier la sémantique Core. |
| CT-008 | Négociation protocole sans intersection | `UNSUPPORTED_CONTRACT`, aucune exécution. |
| CT-009 | Rôle demandant une capacité non traduisible | `CAPABILITY_NOT_ENFORCEABLE`. |
| CT-010 | Même bundle compilé deux fois | Artefacts byte-identiques. |

## 5. Command Gateway

| ID | Test obligatoire | Résultat attendu |
|---|---|---|
| CG-001 | Commande conforme et autorisée | Reçu `accepted`, une transaction. |
| CG-002 | Payload invalide | Aucun fichier modifié ; JSON Pointer retourné. |
| CG-003 | `expected_revision` obsolète | `CONFLICT`, aucun effet. |
| CG-004 | Même idempotency key et même payload | Même reçu, aucun double effet. |
| CG-005 | Même clé, payload différent | `IDEMPOTENCY_MISMATCH`. |
| CG-006 | Rôle non autorisé | `UNAUTHORIZED`. |
| CG-007 | Gate sans autorisation humaine | `HUMAN_AUTH_REQUIRED`. |
| CG-008 | Autorisation humaine réutilisée | Rejet. |
| CG-009 | Chemin avec `..` ou symlink sortant | Rejet, aucune lecture/écriture externe. |
| CG-010 | stdout CLI | JSON uniquement ; diagnostics sur stderr. |
| CG-011 | Evidence créée puis tentative d’update | Commande inexistante/rejet ; octets inchangés. |
| CG-012 | RuntimeResult `succeeded` sans commande | Aucun état métier modifié. |

## 6. Machines à états et autorité

- Tester chaque transition Work Unit permise et chaque transition interdite.
- Tester que `done` exige les outcomes, preuves, revue, audit et acceptation définis par le risque.
- Tester que le changement de SHA invalide ou rend non satisfaisantes les preuves liées à l’ancien SHA.
- Tester Decision Request `pending_human` vers `decided`/`cancelled` et l’interdiction des retours illégaux.
- Tester Observation selon la machine retenue ; aucun statut ne peut être sauté sans règle explicite.
- Tester qu’un signal Feedback ne change aucune gate, phase ou acceptance.
- Tester que Release prépare mais ne décide jamais G3.
- Tester que G4 ne produit `completed` que lorsque toutes les préconditions projet sont satisfaites.

Identifiants dédiés (ajoutés après audit indépendant, pour tracer explicitement deux obligations jusque-là couvertes seulement en prose) :

| ID | Test obligatoire | Résultat attendu |
|---|---|---|
| SM-001 | G4 déclenché alors qu'une Work Unit requise n'a ni preuve, ni revue, ni audit, ni acceptation | Rejet ; `phase` ne passe pas à `completed` ; aucun état modifié. |
| SM-002 | G4 déclenché avec toutes les préconditions du projet effectivement satisfaites | `phase` passe à `completed` ; reçu détaillant les préconditions vérifiées. |

Ces tests sont générés depuis une table normative de transitions, pas dupliqués manuellement dans chaque handler.

## 7. Transactions et récupération

Des failpoints déterministes interrompent le processus : avant journal, après journal, après chaque temporaire, après chaque remplacement, avant événements et après événements.

| ID | Scénario | Invariant |
|---|---|---|
| TX-001 | Arrêt avant premier remplacement | État initial intact après recovery. |
| TX-002 | Arrêt entre deux Agrégats | Recovery produit entièrement avant ou entièrement après, jamais un mélange validé. |
| TX-003 | Arrêt avant Domain Events | État commit et événement complété une seule fois par recovery. |
| TX-004 | Double recovery | Idempotent. |
| TX-005 | Verrou déjà détenu | Timeout/erreur propre, aucune écriture. |
| TX-006 | Hash du journal altéré | `TRANSACTION_RECOVERY_REQUIRED`, aucune réparation spéculative. |
| TX-007 | Deux Gate Decisions même microseconde simulée | Deux noms uniques, aucune perte. |
| TX-008 | Espace disque/permission refusée simulés | Rollback ou état récupérable, diagnostic précis. |
| TX-009 | Arrêt **pendant** l'écriture du fichier journal lui-même (avant son remplacement atomique), distinct d'un journal complet puis falsifié (TX-006) | `recover` traite l'absence de journal valide comme s'il n'existait pas : retour à l'état initial, aucune tentative de réparation spéculative. |

## 8. Domain Events, Requests et messages

- Tout Domain Event est au passé, sans champ `status`, create-exclusive et lié à une transaction commit.
- Une commande rejettée ne produit aucun Domain Event métier.
- Un retry idempotent ne duplique pas l’événement.
- Requests et Workflow Messages valident leurs propres schémas et ne sont pas acceptés dans le dossier `events/domain/`.
- `outcomes.defects` reçoit un type de référence explicite et refuse une référence de mauvaise nature.

## 9. Suite universelle de conformité Adaptateur

Tout Adaptateur fournit un harness implémentant `describe`, `check_compatibility`, `compile`, `execute` et `collect`.

| ID | Test | Exigence |
|---|---|---|
| AD-001 | Descriptor valide | Versions et capacités exactes. |
| AD-002 | Compilation bundle valide | Artifact Manifest complet, chemins sous staging. |
| AD-003 | Compilation déterministe | Même entrée = mêmes hashes. |
| AD-004 | Capacité plus restrictive disponible | Acceptée et rapportée. |
| AD-005 | Capacité requise impossible | Blocage explicite avant exécution. |
| AD-006 | Rôle product readonly | Aucune édition produit possible dans le harness. |
| AD-007 | `RecordObservation` médié | Observation créée sans élargir l’écriture produit. |
| AD-008 | Approbation obligatoire | Impossible de la transformer en auto-approbation. |
| AD-009 | RuntimeResult complet | Identités, timestamps et SHA présents/valides. |
| AD-010 | Texte agent mensonger « done » | Aucun état Core modifié. |
| AD-011 | Timeout/cancel | RuntimeResult terminal exact, reprise déterministe. |
| AD-012 | Artefact pointant hors staging | Rejet. |
| AD-013 | Bundle hash inattendu | Exécution refusée. |
| AD-014 | Isolation requise indisponible | Blocage, jamais dégradation silencieuse. |

Claude Code et Codex ne sont pas déclarés conformes tant qu’ils n’implémentent pas et ne passent pas cette suite.

## 10. Parité Cursor

### Artefacts

- Neuf Rôles métier et Control Plane compilés avec mandats équivalents.
- `auth-smoke` reste un artefact interne Cursor.
- Skills `compile-project`, `orchestrator`, `build-context`, `impact-analysis`, `verify-work-unit`, `audit-release`, `prepare-acceptance`, `propose-profile`, `capture-feedback`, `frontend-design`, `webapp-testing` présents selon leur propriété/licence.
- Hooks, permissions, CLI config et rules valides pour la version Cursor supportée.

### Parcours de référence

1. Installation fraîche du projet témoin.
2. Preflight et diagnostic.
3. Compilation et attente G1.
4. G1 humain.
5. Délégation Backend et/ou Frontend sur branche/worktree isolé.
6. QA, Reviewer, Sécurité/Auditeur selon risque sur SHA stable.
7. Invalidation après changement de SHA.
8. Préparation release et G3 humain.
9. Acceptation/G4 humaine.
10. Observation readonly médiée, rétrospective, revue et export/submit sous ADR-009.

À chaque étape, comparer objets, décisions, preuves, codes de sortie et capacités au comportement attendu ; ne pas exiger l’identité textuelle des réponses IA.

### Cas Windows

Tester explicitement le runtime disponible sur Windows natif. Si `workspace_readonly` ne peut pas être garanti, le scénario nécessitant cette garantie doit être bloqué ou exécuté dans un environnement qualifié ; le test ne peut pas être marqué conforme par simple avertissement.

## 10bis. Migration de schéma des objets mutables (ajouté après audit indépendant)

| ID | Test obligatoire | Résultat attendu |
|---|---|---|
| MIG-001 | Objet Gouvernance legacy sans `revision`/`created_at`/`updated_at`, timestamp absent | `revision: 1` assigné, horodatage de migration consigné avec sa provenance dans le backup et le reçu ; aucune valeur métier absente n'est inventée pour un autre champ obligatoire. |
| MIG-002 | Objet legacy où un champ métier obligatoire (hors `revision`/timestamps) est absent et non déductible | Migration arrêtée avec diagnostic précis ; fichier original préservé intact ; aucune valeur par défaut silencieuse. |

## 11. Distribution

| ID | Test obligatoire | Résultat attendu |
|---|---|---|
| DI-001 | Installation fraîche | Tous composants, manifeste v2 écrit en dernier. |
| DI-002 | Dry-run | Zéro mutation, plan complet. |
| DI-003 | Migration manifeste v1 | Tous les `managed_files` classés et conservés. |
| DI-004 | Fichier project-owned modifié | Préservé byte pour byte. |
| DI-005 | Fichier managed obsolète non modifié | Supprimé/archivé selon politique. |
| DI-006 | Fichier managed localement modifié | Conflit explicite, backup, aucune perte silencieuse. |
| DI-007 | Chemin ancien non classable | Migration bloquée, fichier préservé. |
| DI-008 | Adaptateur actif absent | Validation échoue. |
| DI-009 | Versions incompatibles | Mise à jour refusée avant copie. |
| DI-010 | Échec validation post-copie | Rollback complet, ancien manifeste restauré. |
| DI-011 | Cible Git sale | Refus par défaut ; override explicite testé. |
| DI-012 | Mise à jour répétée | Idempotente. |
| DI-013 | Désinstallation Adaptateur Cursor future | Ne touche ni Core ni données projet. |
| DI-014 | Backup de migration | Hashes vérifiables et restauration testée. |

## 12. Tests d’architecture

- Aucun import `governed_ai.core` vers `adapters.cursor` ou Distribution.
- Aucune chaîne `Cursor`, `.cursor`, `Claude Code`, `Codex`, `hooks.json`, `permissions.json` dans Core, schémas Core ou bundle, hors fixtures négatives et documentation comparative.
- Aucun accès direct aux dossiers d’Agrégats depuis l’Adaptateur.
- Aucun script CLI ne contient de règle métier au-delà du parsing et de l’appel de module.
- Chaque fichier géré appartient exactement à un composant ; aucun chevauchement de manifestes.

## 13. Tests de sécurité

- Traversée de chemin, symlink, injection de nom de fichier et contenu YAML hostile.
- Commande shell non allowlistée et réseau refusé.
- Fuite de secrets dans RuntimeResult, logs et erreurs.
- Usurpation de `role_id`, `execution_id` ou `human_authorization`.
- Modification d’un bundle publié ou d’une Evidence.
- Course entre deux commandes avec même révision.
- Export hors workspace, ou remount alors que `telemetry.collection` est `disabled` / termes non acceptés.

Les tests vérifient le refus et l’absence d’effet, pas seulement le message d’erreur.

## 14. Fixtures et reproductibilité

- Horloge et UUID injectables dans les tests.
- Fixtures v0.4 immuables accompagnées de hashes.
- Fake Adapter déterministe pour tester Core sans Cursor.
- Fake Core pour tester l’Adaptateur sans données réelles.
- Aucun appel réseau dans L0–L3.
- Les résultats de tests réels Cursor enregistrent versions outil/OS et capacités observées.

## 15. Critères de release

- L0–L3 : 100 % des tests obligatoires réussissent, aucun skip non justifié.
- L4 : parcours Cursor réel réussi sur chaque plateforme déclarée supportée, ou plateforme retirée du descriptor.
- L5 : gates et consentements vérifiés par un humain autre que l’implémenteur principal.
- Zéro violation d’architecture ou perte de fichier dans les tests Distribution.
- Zéro transition autoritaire fondée uniquement sur un RuntimeResult.
- Rapport de conformité signé avec versions Core, Adaptateur, bundle, OS et Cursor.

La couverture de lignes est informative. La preuve principale est la couverture des invariants, transitions, erreurs et failpoints.

## 16. Format du rapport

```json
{
  "core_version": "0.5.0",
  "protocol_version": "1.0",
  "bundle_version": "1.0.0",
  "adapter": {"id": "cursor", "version": "0.5.0"},
  "environment": {"os": "windows", "tool_version": "<cursor-version>"},
  "levels": {"L0": "passed", "L1": "passed", "L2": "passed", "L3": "passed", "L4": "passed", "L5": "passed"},
  "failures": [],
  "deviations": [],
  "generated_at": "2026-08-28T12:00:00Z"
}
```

## 17. Limites

- Les comportements probabilistes d’un modèle exigent des assertions sur artefacts et invariants, pas sur formulation textuelle exacte.
- La disponibilité d’un runner Cursor réel en CI doit être organisée avant la release ; une simulation ne remplace pas L4.
- Les tests ne remplacent pas la revue de sécurité des primitives natives de chaque version d’outil.
