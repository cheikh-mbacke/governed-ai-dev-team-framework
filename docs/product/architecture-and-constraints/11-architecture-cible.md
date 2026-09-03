# Document 11 — Spécification technique : architecture cible

**Statut** : version 1.1 — normative pour la refonte (audit technique indépendant du 28 août 2026 appliqué : précision failpoint §7.3). Les termes **DOIT**, **NE DOIT PAS**, **DEVRAIT** et **PEUT** expriment respectivement une obligation, une interdiction, une recommandation forte et une option.

## 1. Décisions structurantes

| ID | Décision | Conséquence |
|---|---|---|
| ADR-001 | Les fichiers d’état transactionnels restent la source de vérité. | La refonte n’introduit pas d’event sourcing. Project State et les Agrégats persistés sont autoritaires. |
| ADR-002 | Les Domain Events sont un journal append-only post-commit. | Ils servent à l’audit et aux intégrations, mais le système n’affirme pas pouvoir reconstruire tout l’état depuis eux en v1. |
| ADR-003 | Toute mutation autoritaire passe par un Command Gateway du noyau. | Aucun Adaptateur ni agent ne modifie directement Work Units, Project State, décisions, preuves ou feedback. |
| ADR-004 | La persistance reste YAML/JSON lisible par l’humain. | Une unité de travail fichier + verrou + journal de transaction assure validation, récupération et idempotence. |
| ADR-005 | Rôles et Procédures sont publiés dans un bundle atomique versionné. | L’Adaptateur compile une révision exacte ; les références croisées sont vérifiées avant publication. |
| ADR-006 | La sortie native d’un agent est opérationnelle, non autoritaire. | Un `RuntimeResult` réussi ne déclenche aucune transition sans commande noyau valide. |
| ADR-007 | L’Adaptateur Cursor est le seul Adaptateur livré par cette refonte. | Claude Code et Codex ne sont utilisés que comme contrôles de portabilité du contrat. |
| ADR-008 | Session Cloud reste hors périmètre. | Aucun compte distant, synchronisation mobile ou surface Session Cloud n’est ajouté. |
| ADR-009 | Remontée Feedback liée à l’usage. | **Installer ou utiliser le framework vaut acceptation.** Le choix de l’adoptant est d’utiliser le framework ou de ne pas l’utiliser — pas un mode « privacy » intermédiaire. Sous `telemetry.collection: consented_share` (défaut à l’install), le projet **DOIT** transmettre un Feedback Export **complet** (y compris `project_id`, texte libre, exécutions) vers `telemetry.submit_url` sans anonymisation, sans niveau `structured` imposé et sans `human_authorization` par export. Seul `collection: disabled` coupe la remontée (cas exceptionnel hors ligne). Ce canal unidirectionnel n’est **pas** Session Cloud. |

## 2. Architecture logique

```text
                    HUMAN OPERATOR
                         │ gates / consent
                         ▼
┌─────────────────────────────────────────────────────────┐
│ GOVERNANCE CORE                                         │
│ Contract Bundle │ Command Gateway │ Aggregates │ Store  │
│ Validation      │ Policies        │ Audit log  │ Queries │
└───────────────┬───────────────────────────┬─────────────┘
                │ Adapter SPI               │ read model
                ▼                           ▼
┌──────────────────────────────┐   ┌──────────────────────┐
│ CURSOR ADAPTER               │   │ FEEDBACK             │
│ compiler │ launcher │ mapper │   │ observations/reports │
└───────────────┬──────────────┘   └──────────────────────┘
                │ native artifacts
                ▼
             CURSOR

┌─────────────────────────────────────────────────────────┐
│ DISTRIBUTION                                            │
│ install │ migrate │ validate │ rollback │ manifest v2  │
└─────────────────────────────────────────────────────────┘
```

Feedback est un module du déploiement du noyau mais conserve son modèle et ses commandes propres. Distribution dépend des manifestes publiés par Core et Cursor ; ni Core ni Cursor ne dépendent de Distribution.

## 3. Arborescence source cible

```text
src/governed_ai/
  core/
    commands/            # handlers et règles d’autorité
    domain/              # modèles et machines à états
    persistence/         # verrous, transactions, repositories
    queries/             # lectures sans mutation
    events/              # Domain Events post-commit
  feedback/
    commands/
    domain/
  contracts/
    schemas/             # schémas du protocole et du bundle
    compatibility.py
  adapters/
    spi.py               # interfaces agnostiques
adapters/cursor/
  manifest.json
  compiler/              # bundle → fichiers Cursor
  templates/
    .cursor/
  runtime/               # collecte RuntimeResult, diagnostics
distribution/
  installer/
  migrations/
  schemas/
scripts/ai-team/
  gov.py                 # CLI stable du Command Gateway (RecordGateDecision, etc.)
  validate.py            # wrapper compatible
  feedback.py            # wrapper compatible
tools/install.py         # wrapper Distribution
tests/
  core/ adapters/ distribution/ conformance/ fixtures/
```

`scripts/ai-team/` ne contient plus de logique métier : uniquement des points d’entrée stables vers les modules testables.

## 4. Arborescence installée cible

```text
.ai-team/
  constitution/                 # core-managed
  schemas/                      # core-managed
  contracts/
    active-bundle.json          # core-managed, pointeur
    bundles/<version>/...       # core-managed, immuable
  runtime/governed_ai/...       # core-managed runtime Python
  state/ project-profile.yaml sources/
  work-units/ decisions/ evidence/ findings/ acceptance/
  releases/ context-packages/ observations/ retrospectives/
  events/domain/                # append-only
  metrics/ logs/ audits/
  .transactions/               # récupération technique, ignoré par Git
  locks/                        # verrous techniques, ignoré par Git
  installation-record.json     # distribution-managed
.cursor/                        # adapter:cursor-managed
scripts/ai-team/*.py            # wrappers core/distribution-managed
AGENTS.md                       # core-managed, agnostique
```

Chaque chemin DOIT avoir un propriétaire unique dans `installation-record.json` : `core`, `adapter:cursor`, `distribution` ou `project`. Les données runtime sont `project` et ne sont jamais écrasées par une mise à jour.

## 5. Règles de dépendance

1. `core` NE DOIT PAS importer `adapters.cursor` ou `distribution`.
2. `feedback` PEUT importer les identifiants et interfaces de lecture de `core`, jamais ses repositories concrets.
3. `adapters.cursor` dépend seulement de `contracts` et du SPI d’Adaptateur.
4. `distribution` lit les manifestes de composants ; il n’importe aucune règle de domaine.
5. Les fichiers sous `.cursor/` NE DOIVENT PAS être référencés par les schémas ou politiques du noyau.
6. Les migrations d’état projet utilisent une API de migration dédiée ; elles NE DOIVENT PAS appeler des handlers runtime avec une fausse identité humaine.

Un test d’architecture inspecte les imports Python et les références textuelles interdites.

## 6. Command Gateway et lectures

Le port local stable est :

```text
python scripts/ai-team/gov.py command --input <commande.json>
python scripts/ai-team/gov.py query <nom> [options]
python scripts/ai-team/gov.py validate [--all]
python scripts/ai-team/gov.py recover
```

- `command` valide identité, autorité, schéma, révision attendue et invariants avant mutation.
- `query` est sans effet de bord et retourne du JSON sur stdout.
- `validate` vérifie données, bundles, manifeste et frontières.
- `recover` termine ou annule une transaction interrompue de façon déterministe.

Les wrappers historiques appellent ce port pendant la fenêtre de migration.

## 7. Persistance transactionnelle fichier

### 7.1 Mutable

Tout Agrégat mutable v2 porte `revision` entier, `created_at` et `updated_at`. Une commande fournit `expected_revision`; une divergence retourne `CONFLICT` sans écrire.

### 7.2 Immuable

Evidence, Domain Event, Gate Decision audit et révisions de bundle sont créés avec un identifiant unique et une opération create-exclusive. Aucune commande `update` n’existe.

### 7.3 Unité de travail

Sous un verrou projet exclusif :

1. lire les versions courantes ;
2. valider la commande ;
3. construire tous les futurs fichiers en mémoire ;
4. valider chaque payload par schéma et invariants croisés ;
5. écrire un journal sous `.ai-team/.transactions/<transaction_id>/` avec hashes avant/après ;
6. écrire les temporaires sur le même volume ;
7. remplacer les fichiers ;
8. créer les Domain Events post-commit ;
9. marquer la transaction `committed`, puis nettoyer selon la rétention.

Si le processus s’arrête aux étapes 5–8, `recover` utilise le journal pour finir ou restaurer. Aucun état partiel ne doit être accepté par `validate`.

L’étape 5 elle-même DOIT être atomique (écriture d’un fichier journal temporaire suivie d’un remplacement atomique), afin qu’un arrêt pendant l’écriture du journal ne laisse jamais un journal partiellement écrit et syntaxiquement invalide : `recover` DOIT alors se comporter comme si aucun journal n’existait (retour à l’état initial), et non tenter de le réparer. Ce cas — arrêt **pendant** l’écriture du journal — est distinct d’un journal complet mais falsifié après coup ; les deux DOIVENT être testés séparément (voir Document 14, TX-006 et TX-009).

## 8. Sécurité et autorité

- L’identité déclarée par l’agent n’est pas digne de confiance seule. L’Adaptateur crée un `execution_id` et associe le Rôle résolu.
- Le Command Gateway vérifie la commande contre les capacités de la révision du Rôle.
- Les gates, acceptations et exports sensibles exigent une `human_authorization` non réutilisable, créée par une action humaine locale explicite.
- Un Rôle `product_write=none` peut soumettre `RecordObservation` sans obtenir une capacité d’écriture générale : l’écriture est effectuée par le processus noyau.
- Les chemins fournis sont résolus sous la racine projet, sans traversée `..` ni lien symbolique sortant.
- Les logs ne contiennent ni secrets, ni contenu complet d’export, ni jetons d’autorisation.

## 9. Observabilité

Chaque commande émet un reçu contenant `command_id`, `transaction_id`, acteur, type, résultat, objets affectés et Domain Events. Les logs techniques et le journal métier sont séparés. Un identifiant de corrélation relie RuntimeResult, commandes et événements.

## 10. Exigences non fonctionnelles

- Python 3.10 minimum, PyYAML et jsonschema conservés.
- Exécution locale hors ligne par défaut.
- Formats UTF-8 et timestamps UTC RFC 3339.
- Écritures déterministes autant que possible ; compilateur Cursor reproductible.
- Compatibilité Windows, macOS et Linux ; les garanties de sandbox propres à l’OS sont rapportées, jamais supposées.
- Aucune régression silencieuse : une capacité non traduisible bloque l’exécution avant lancement.

## 11. Limites et décisions différées

- Les verrous réseau/NFS ne sont pas garantis en v1 ; le projet doit être sur un système de fichiers local supportant le remplacement atomique.
- Le journal post-commit n’est pas une base event-sourced.
- Le format d’autorisation humaine est local ; toute délégation distante appartient à Session Cloud et reste hors périmètre.
- L’éventuelle publication en package PyPI est différée ; le runtime peut d’abord être livré comme source gérée.
