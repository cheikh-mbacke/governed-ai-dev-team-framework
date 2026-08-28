# Document 1 — Langage ubiquitaire

**Statut** : version 1.1 corrigée. Une entrée est qualifiée **observée**, **règle** ou **cible** afin de ne pas confondre schéma, politique et conception future.

## 1. Gouvernance

| Terme | Définition | Qualification |
|---|---|---|
| **Work Unit** | Unité de travail gouvernée portant scope, dépendances, risque, statut, vérifications, résultats et références de preuve. | Observé dans `work-unit.schema.json`. « Plus petite unité » est une règle de méthode, pas une propriété du schéma. |
| **Project State** | Enregistrement persistant de la phase, des gates, des Work Units et de différents compteurs ou références projet. | Observé. Il est directement modifié ; aucun projecteur complet ne permet aujourd’hui de le qualifier d’état entièrement dérivé. |
| **Phase** | Une valeur parmi `not_compiled`, `readiness_blocked`, `awaiting_g1_approval`, `execution`, `verification`, `release_candidate`, `human_acceptance`, `completed`, `paused`. | Observé. |
| **Gate** | Point d’approbation humaine G0 à G4. | Règle de Gouvernance soutenue par les scripts et politiques. |
| **Gate Decision** | Trace persistée d’une décision humaine de gate. | Observé. Ce n’est pas actuellement une source événementielle immuable ou rejouable. |
| **Decision Request** | Question adressée à une autorité humaine, avec options et statut `pending_human`, `decided` ou `cancelled`. | Observé dans le schéma ; writer et convention de nom exacts non observés. |
| **Evidence** | Enregistrement d’un résultat observé, de ce qu’il démontre et de ses limites. | Observé. Son absence de `status` ne suffit pas à garantir son immutabilité. |
| **Finding** | Constat d’audit avec sévérité, classification et statut. | Observé. |
| **Context Package** | Contexte assemblé pour une Work Unit et un rôle, réparti en niveaux L0 à L3 avec provenance et justification. | Observé. |
| **Constitution** | Ensemble versionné de politiques gouvernant autorité, staffing, capacités, vérification, revue, audit, release et gates. | Observé. |
| **Human Construction Material** | Sources humaines faisant autorité : intention, règles métier, exigences, contraintes et critères d’acceptation. | Règle de domaine. |
| **Release Candidate** | Enregistrement préparatoire d’un candidat de release. | Observé. |
| **Acceptance** | Enregistrement d’une acceptation humaine. | Observé. |

## 2. Contrat publié et Adaptateur/Runtime

| Terme | Définition | Qualification |
|---|---|---|
| **RoleId** | Identité stable d’un mandat, par exemple `backend-developer`. | Cible. |
| **RoleDefinitionRevision** | Définition immuable et versionnée du mandat, des capacités, approbations, procédures et outils d’un Rôle. | Cible. |
| **ProcedureId** | Identité stable d’une procédure. | Cible. |
| **ProcedureRevision** | Définition immuable et versionnée de son intention, entrées, étapes, sorties et invariants. | Cible. |
| **Published Contract Bundle** | Ensemble atomique et versionné de définitions de Rôles et Procédures dont les références croisées ont été validées. | Cible. |
| **Adaptateur** | Composant traduisant le contrat publié vers les primitives d’un outil et ramenant les résultats vers les ports du noyau. | Cible ; Cursor n’est pas encore isolé comme tel. |
| **Runtime Result** | Résultat opérationnel brut ou textuel d’une exécution native. Il peut être lu pour orchestrer, mais ne suffit pas à prouver la réussite ni à modifier l’état faisant autorité. | Cible. |
| **AGENTS.md** | Point d’entrée d’instructions de dépôt compris par Codex et accepté par Cursor comme alternative simple aux rules. | Observé ; sa place future doit être classée explicitement. |
| **Politique de capacité** | Actions techniquement possibles : lecture/écriture, commandes, réseau et outils externes. | Cible agnostique. Dans Cursor actuel, elle est répartie entre `readonly`, `permissions.json`, `cli.json` et les primitives de sandbox du produit. |
| **Politique d’approbation** | Actions nécessitant une approbation humaine même si elles sont techniquement possibles. | Cible agnostique. |
| **MCP** | Protocole d’exposition d’outils et de systèmes externes. | Primitive disponible dans les outils étudiés ; non intégrée au modèle actuel du noyau. |
| **Hook** | Réaction configurée à un événement du cycle de vie d’exécution. | Primitive documentée chez Cursor, Claude Code et Codex au 28 août 2026 ; le contrat ne doit néanmoins pas en faire son unique mécanisme de sûreté. |

## 3. Feedback / Apprentissage

| Terme | Définition | Qualification |
|---|---|---|
| **Observation** | Signal structuré de friction ou d’apprentissage. | Observé. Le schéma accepte plusieurs statuts, mais le script actuel ne met pas à jour une Observation existante. |
| **Retrospective** | Snapshot de synthèse généré pour une Work Unit ou un projet. | Observé. Le scope `increment` n’existe ni dans le schéma ni dans le CLI actuel. |
| **Feedback Export** | Export JSON d’observations et de rétrospectives, complet ou anonymisé. | Observé. Il est persisté par défaut sous `.ai-team/metrics/`; le consentement humain est une règle cible non encore imposée. |

## 4. Distribution

| Terme | Définition | Qualification |
|---|---|---|
| **Project Profile** | Identité et configuration fonctionnelle du projet, comprenant à terme l’identifiant de l’Adaptateur actif. | Observé + extension cible. |
| **Source Registry** | Registre explicite des sources produit faisant autorité. | Observé. |
| **Installation Record** | Manifeste des versions du noyau et des Adaptateurs, des fichiers gérés et des horodatages d’installation. | Cible à partir de `framework-version.json`. |

## 5. Limites

- Les capacités des outils évoluent ; toute matrice comparative doit être datée et fondée sur des sources officielles.
- Les termes tactiques prospectifs n’affirment pas l’existence de leurs implémentations.
- Les règles d’immutabilité et de transition exigent des commandes et repositories qui les imposent ; un schéma seul ne les garantit pas.

## Sources

Schémas sous `.ai-team/schemas/`, `AGENTS.md`, `.cursor/agents/`, `.cursor/permissions.json`, `.cursor/cli.json`, `scripts/ai-team/feedback.py`, documentations officielles Cursor, Claude Code et Codex consultées le 28 août 2026.
