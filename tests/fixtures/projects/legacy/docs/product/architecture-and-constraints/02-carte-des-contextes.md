# Document 2 — Carte des contextes

**Statut** : version 1.1 corrigée. Cette carte décrit une **cible** ; les frontières ne sont pas encore matérialisées dans le dépôt.

## 1. Sous-domaines et contextes bornés

Core/Supporting/Generic qualifie les **sous-domaines**. Un Bounded Context est une frontière de modèle et de langage. La cible retient volontairement un contexte borné principal par sous-domaine, sans prétendre que ces notions sont synonymes.

| Bounded Context cible | Sous-domaine | Responsabilité et propriété |
|---|---|---|
| **Gouvernance** | Core | Work Unit, état projet, gates, décisions humaines, preuves, constats, acceptation, contrats agnostiques de Rôles et Procédures. |
| **Adaptateur / Runtime** | Supporting | Compilation des contrats publiés en artefacts natifs, exécution, traduction des capacités et retour vers les ports du noyau. |
| **Feedback / Apprentissage** | Supporting | Observations, rétrospectives et exports ; aucune autorité sur les décisions de Gouvernance. |
| **Distribution / Installation** | Generic | Installation, mise à jour, migration, rollback, versions et possession des fichiers. |

Gouvernance possède `RoleId`, `RoleDefinitionRevision`, `ProcedureId`, `ProcedureRevision` et le `PublishedContractBundle`. Adaptateur possède les artefacts natifs et leur compilation. Cette décision remplace l’attribution contradictoire de Rôle et Procédure à l’Adaptateur.

## 2. Relations cibles

```text
GOUVERNANCE
  ├── Published Language + port stable ──▶ ADAPTATEUR/RUNTIME
  │                                      ACL côté Adaptateur
  ├── identifiants/lectures ────────────▶ FEEDBACK
  └── contrats de possession/version ───▶ DISTRIBUTION

ADAPTATEUR/RUNTIME
  ├── signaux d’exécution ──────────────▶ FEEDBACK
  └── manifestes/emplacements natifs ──▶ DISTRIBUTION
```

| Amont → aval | Pattern cible | Précision |
|---|---|---|
| Gouvernance → Adaptateur | **Published Language** et port stable ; **ACL** côté Adaptateur | Les schémas et contrats peuvent former le langage publié. Le terme **Open Host Service** ne sera employé qu’une fois un protocole/service stable réellement exposé. |
| Gouvernance → Feedback | **Conformist** limité | Feedback adopte les identifiants Gouvernance, mais possède son propre modèle de synthèse. |
| Gouvernance → Distribution | **Conformist** côté Distribution | Distribution consomme les règles publiées de version et de possession sans redéfinir le domaine. |
| Adaptateur → Distribution | **Conformist** côté Distribution | Distribution adopte les emplacements et manifestes publiés par l’Adaptateur. Cette orientation corrige la relation inversée antérieure. |
| Adaptateur → Feedback | Fournisseur/consommateur simple | Les signaux passent par un port de Feedback ; aucun partage implicite de modèle natif de l’outil. |

## 3. Frontières cibles

### Gouvernance

- ne référence aucune primitive nommée d’un outil ;
- valide et persiste l’état faisant autorité ;
- publie les contrats agnostiques ;
- ne considère pas une sortie brute d’agent comme preuve suffisante.

### Adaptateur / Runtime

- connaît le contrat publié et les primitives de son outil ;
- ne crée aucun statut métier propre ;
- ne modifie l’état faisant autorité qu’en invoquant un port/une commande du noyau ;
- signale explicitement toute capacité impossible à traduire.

### Feedback / Apprentissage

- lit les références nécessaires ;
- produit des signaux et synthèses ;
- ne décide ni gate, ni acceptation, ni résolution produit.

### Distribution / Installation

- préserve les fichiers possédés par le projet ;
- peut exécuter des migrations explicites et transactionnelles ;
- ne réalise pas de mutation d’état métier hors d’une migration publiée et validée.

## 4. État actuel observé

- `.cursor/agents/*.md` mélange mandat et frontmatter Cursor.
- La Constitution contient des références Cursor dans `35-ui-ux-strategy.yaml` et `70-permissions-policy.yaml`.
- Des scripts sous `scripts/ai-team/` connaissent également Cursor.
- `tools/install.py` livre `.cursor` et `.ai-team` comme un seul ensemble.
- L’installateur écrit actuellement `project_id`, `constitution_version`, des données migrées et parfois un événement `CONTRACT_CHANGE`. Ces écritures sont des contraintes héritées à isoler, pas une preuve que la frontière cible existe déjà.

## 5. Limites

- Le Published Language est partiellement esquissé par les schémas ; aucun Open Host Service complet n’est observé.
- Les frontières de code et de persistance restent à concevoir.
- La relation Conformist Feedback devra être réévaluée si son modèle devient fortement divergent de Gouvernance.

## Sources

`.ai-team/constitution/`, `.cursor/agents/`, `scripts/ai-team/`, `tools/install.py`, schémas sous `.ai-team/schemas/`, DDD Reference d’Eric Evans.
