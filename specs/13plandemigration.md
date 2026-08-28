# Document 13 — Spécification technique : plan de migration

**Statut** : version 1.1 — spécification normative du passage de l’architecture 0.4.x vers la cible (audit technique indépendant du 28 août 2026 appliqué : échec de traduction wrapper précisé §7). La migration est incrémentale, réversible par étape et ne construit ni Session Cloud ni les Adaptateurs Claude/Codex.

## 1. Principes

1. Aucun big bang : chaque phase produit un dépôt installable et testable.
2. Les comportements 0.4.0 sont capturés par des tests de caractérisation avant déplacement du code.
3. Les fichiers possédés par le projet ne sont jamais remplacés par une copie du framework.
4. Tout changement de schéma possède migration, validation avant/après et rollback.
5. Les wrappers CLI existants restent fonctionnels pendant une version mineure de transition.
6. L’Adaptateur Cursor atteint la parité avant suppression des artefacts historiques.
7. Une phase ne commence qu’après satisfaction de la sortie de la phase précédente.

## 2. Versions proposées

| Version | Objet |
|---|---|
| `0.4.x` | Baseline actuelle et éventuels correctifs sans refonte. |
| `0.5.0-alpha` | Modules Core, contrats v1 et wrappers, non recommandé à l’installation générale. |
| `0.5.0-beta` | Adaptateur Cursor compilé, Command Gateway et migrations testés sur projets témoins. |
| `0.5.0` | Première version refondue supportée ; manifeste d’installation v2. |
| `0.6.0` | Suppression éventuelle des chemins dépréciés après télémétrie locale/tests et annonce. |

Le `protocol_version` reste indépendant de la version du framework.

## 3. Phase 0 — Baseline et gel comportemental

### Travaux

- Étiqueter la révision 0.4.x servant de référence.
- Exécuter la suite actuelle et conserver le résultat attendu.
- Ajouter des fixtures représentatives pour Project Profile, Project State, Work Unit, Gate Decision, Observation, Retrospective et manifeste installé.
- Capturer les sorties et codes de retour de `validate.py`, `record_gate.py`, `feedback.py`, `check_done.py`, `preflight.py`, `diagnose.py`, `status.py` et `tools/install.py`.
- Inventorier chaque fichier livré avec son propriétaire réel.
- Créer un projet témoin propre et un projet témoin contenant données runtime, fichiers obsolètes gérés et changements utilisateur.

### Sortie

- Tous les tests 0.4.x verts.
- Golden fixtures versionnées.
- Aucun comportement non caractérisé dans les parcours critiques installation, gate, done et feedback.

## 4. Phase 1 — Introduire les modules sans changer les comportements

### Travaux

- Créer `src/governed_ai/core`, `feedback`, `contracts` et `adapters/spi.py`.
- Déplacer progressivement `common.py` et `feedback_common.py` vers des modules importables.
- Garder les scripts historiques comme wrappers.
- Centraliser racine projet, lecture YAML/JSON, validation de schéma, timestamps, identifiants et écriture atomique.
- Interdire les imports Core → Cursor par test d’architecture.

### Règle

À cette phase, aucune forme de données installée ne change. Les golden tests doivent rester identiques, sauf diagnostics explicitement documentés.

### Sortie

- Parité des CLI historiques.
- Les fonctions métier ne dépendent plus de `Path(__file__).parents[2]` sans abstraction de workspace.
- Les modules Core ne contiennent aucune chaîne `.cursor`, `Cursor`, `hooks.json`, `permissions.json` ou `cli.json`.

## 5. Phase 2 — Published Contract Bundle v1

### Travaux

- Créer les schémas manifest, RoleDefinitionRevision et ProcedureRevision.
- Transcrire les neuf Rôles métier et le Control Plane depuis les Documents 5–6 corrigés.
- Transcrire les Procédures existantes en contenu agnostique ; isoler les étapes réellement propres à Cursor dans le compilateur.
- Publier `bundle_version: 1.0.0` avec hash canonique.
- Ajouter validation atomique et test des références croisées.
- Ajouter au handoff les identités bundle/Rôle/Procédure exactes.

### Compatibilité

Pendant cette phase, les fichiers `.cursor/agents` et `.cursor/skills` restent les artefacts exécutés. Un test compare leur contenu sémantique au bundle et signale les divergences.

### Sortie

- Bundle valide et immuable.
- Aucun Rôle ne référence une Procédure absente.
- Les trois axes d’écriture sont présents pour chaque Rôle.

## 6. Phase 3 — Command Gateway et persistance sûre

### Ordre d’introduction

1. Infrastructure `command`, reçus, idempotence, verrou et récupération.
2. `RecordObservation` et `RegisterEvidence`, à faible couplage.
3. Work Unit : création et transitions.
4. Decision Request et Finding.
5. Gate Decision, Acceptance et Release Candidate.
6. Retrospective et export avec autorisation humaine.

### Migration des objets mutables

Les schémas v2 ajoutent `revision`, `created_at` et `updated_at`. Migration déterministe :

- objet existant sans `revision` → `revision: 1` ;
- timestamp déjà présent → réutilisé si conforme ;
- timestamp absent → horodatage de migration consigné dans le backup et le reçu ;
- aucune valeur métier n’est inventée pour satisfaire un champ obligatoire : la migration s’arrête avec diagnostic.

### Gate Decision

- Remplacer le nom à la seconde par `gate-<G>-<UTC-microseconds>-<uuid>.yaml`.
- Appliquer Gate Decision, Project State et Work Unit dans une seule unité de travail récupérable.
- Interdire G4 sans vérification des préconditions d’acceptation.
- Conserver les anciens fichiers sans les réécrire ; ils sont lus comme audit legacy.

### Fenêtre de compatibilité

`record_gate.py` et `feedback.py` traduisent leurs arguments en Command Envelope. Un avertissement de dépréciation va sur stderr, sans casser les scripts automatisés qui lisent stdout.

Si cette traduction elle-même échoue (arguments legacy non convertibles en Command Envelope valide, schéma legacy incompatible avec le nouveau validateur), le wrapper DOIT s'arrêter avant tout appel au Command Gateway, retourner un code de sortie non nul et un message explicite sur stderr, et NE DOIT PAS retomber sur l'ancien comportement d'écriture directe de fichier : un wrapper qui échoue à traduire ne doit jamais silencieusement repasser en écriture non gouvernée. Ce cas est distinct d'un rejet du Command Gateway lui-même (`INVALID_SCHEMA`, etc.), qui est déjà couvert par les codes de sortie du Document 12 §11.

### Sortie

- Aucun writer métier ne contourne le Command Gateway.
- Tests d’arrêt forcé à chaque étape transactionnelle verts.
- Réexécution d’une commande idempotente sans double effet.

## 7. Phase 4 — Extraction de l’Adaptateur Cursor

### 4.1 Manifest et compilateur

- Créer `adapters/cursor/manifest.json`.
- Transformer bundle + profil en `.cursor/agents`, skills, rules, hooks, permissions et configuration CLI.
- Générer dans un staging, valider, puis installer par Distribution.
- Le résultat est déterministe : même entrée, mêmes octets hors champs explicitement horodatés — idéalement aucun.

### 4.2 Stratégie de parité

1. **Shadow compile** : générer sans utiliser ; comparer aux fichiers historiques.
2. **Golden compile** : accepter les différences explicables et figer les nouveaux goldens.
3. **Opt-in** : projet témoin utilisant les fichiers générés.
4. **Default** : l’installation utilise le compilateur Cursor.
5. **Cleanup** : supprimer les duplications historiques seulement après la release stable.

### 4.3 Capacités

- Traduire `product_write` sans augmenter la capacité.
- Pour `RecordObservation` depuis un Rôle readonly, utiliser le port médié du noyau ; ne jamais mettre `readonly: false` comme contournement.
- Produire `CAPABILITY_NOT_ENFORCEABLE` lorsque Windows/runtime ne garantit pas la politique requise.
- Conserver `auth-smoke` dans l’Adaptateur, hors bundle métier.

### Sortie

- Suite de conformité Document 14 entièrement verte.
- Parcours Cursor de référence sans régression fonctionnelle.
- Aucune référence Cursor dans Core ou le bundle agnostique.

## 8. Phase 5 — Distribution et Installation Record v2

### Migration v1 → v2

Entrée legacy :

```json
{"schema_version": 1, "version": "0.4.0", "managed_files": ["..."]}
```

Conversion :

- `core.version`, `adapter:cursor.version` et `distribution.version` reçoivent la version legacy initiale ;
- chaque ancien `managed_file` est classé par les nouveaux manifestes ;
- tout chemin non classable bloque la migration et reste préservé ;
- `installed_at` utilise une valeur existante si disponible, sinon l’heure de migration avec provenance dans le reçu ;
- `last_updated_at` est l’heure du commit de migration ;
- l’ancien manifeste est copié dans `migration-backups/`.
- le Project Profile reçoit `active_adapter_id: cursor` s’il n’existe pas ; une valeur existante inconnue bloque la migration au lieu d’être remplacée ;
- toute ancienne forme `adapter: {id, version}` est sauvegardée, son `id` devient `active_adapter_id` et sa version doit correspondre à l’entrée migrée du manifeste, sinon la migration s’arrête.

### Installation fraîche

- écrit les composants gérés ;
- initialise seulement les données projet nécessaires ;
- écrit `installation-record.json` en dernier ;
- valide `active_adapter_id=cursor` et l’entrée installée.

### Mise à jour

- détecte fichiers obsolètes par propriétaire et `managed_files` ;
- n’efface jamais un fichier project-owned ;
- refuse une cible Git sale sauf autorisation explicite existante ;
- exécute validations et rollback comme aujourd’hui, étendus aux composants séparés.

### Sortie

- Install, update, dry-run et rollback verts sur Windows/Linux/macOS CI disponibles.
- Migration 0.4.0 → 0.5.0 testée avec données réelles synthétiques.
- Aucun `managed_files` perdu.

## 9. Phase 6 — Nettoyage et documentation

- Retirer les références Cursor de la Constitution et des scripts Core.
- Mettre à jour README, Architecture, Security Model, Operator Guide, Upgrading et Adopter Checklist.
- Documenter les dépréciations et leur échéance.
- Supprimer le code mort uniquement après recherche de consommateurs et release stable.
- Ne pas ajouter de stubs Claude/Codex prétendant être des Adaptateurs fonctionnels.

## 10. Matrice de déplacement

| Actuel | Cible | Stratégie |
|---|---|---|
| `scripts/ai-team/common.py` | `src/governed_ai/core/...` | Extraire, conserver wrapper/import compatible. |
| `feedback_common.py`, `feedback.py` | `src/governed_ai/feedback/...` | Extraire puis router par commandes. |
| `record_gate.py` | handler `RecordGateDecision` | Wrapper déprécié. |
| `check_done.py` | invariant/query Work Unit | Conserver wrapper. |
| `preflight.py`, `diagnose.py`, `propose_allowlist.py` | parties Core + `adapters/cursor/runtime` | Séparer les checks génériques des checks Cursor. |
| `.cursor/agents`, skills, rules, hooks | `adapters/cursor/templates` + sortie compilée | Shadow compile puis bascule. |
| `.ai-team/schemas` | schémas Core v2 | Migration explicite, versions conservées. |
| `framework-version.json` | `installation-record.json` v2 | Migration préservant `managed_files`. |
| `tools/install.py` | wrapper `distribution/installer` | Parité CLI avant extension. |

## 11. Rollback

Chaque migration crée un backup manifesté contenant chemin, hash et propriétaire. En cas d’échec :

1. interrompre tout nouveau Command Gateway ;
2. exécuter `recover` pour la transaction courante ;
3. restaurer le snapshot d’installation ;
4. restaurer le manifeste legacy ;
5. relancer le validateur de la version précédente ;
6. produire un diagnostic sans supprimer le backup.

Un rollback de logiciel ne rétrograde pas automatiquement des données déjà créées sous un schéma incompatible. Une migration inverse explicite est requise ou la mise à jour est déclarée non rétrogradable avant consentement humain.

## 12. Risques principaux

| Risque | Prévention |
|---|---|
| Dérive sémantique agents ↔ bundle | Comparaison sémantique et compilateur déterministe. |
| État partiel après crash | Journal de transaction, verrou, récupération et tests de failpoints. |
| Droits readonly élargis | Port médié et tests négatifs de capacité. |
| Suppression de fichiers utilisateur | Propriétaire unique, dry-run, hashes, backups et fixtures de fichiers inconnus. |
| Manifeste v2 incomplet | Migration teste le compte et les hashes de `managed_files`. |
| Différences OS Cursor | Rapport de compatibilité et blocage explicite. |
| Double source de version | `active_adapter_id` sans version dans Project Profile. |

## 13. Définition de fin de migration

- Tous les critères du Document 14 passent.
- Core ne contient aucune dépendance Cursor.
- Cursor est produit et exécuté via le SPI d’Adaptateur.
- Toutes les mutations runtime passent par le Command Gateway.
- Installation Record v2 est utilisé et migrable depuis 0.4.0.
- Un projet témoin complet franchit compilation → G1 → implémentation → vérification → revue/audit → release → acceptation sans régression.
- Les limites résiduelles sont documentées et aucune capacité non prouvée n’est présentée comme garantie.

## 14. Limites

- Les numéros de versions proposés peuvent être ajustés avant la première release, mais l’ordre et les critères de sortie des phases restent obligatoires.
- Le comportement d’un Cursor réel dépend de la version et de la plateforme ; il doit être qualifié par le Document 14.
- Une migration inverse des nouveaux objets v2 n’est pas automatiquement garantie et doit être fournie avant toute mise à jour déclarée rétrogradable.
