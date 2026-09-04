# Document 3 — Modèle tactique : Adaptateur/Runtime

**Statut** : version 1.2 corrigée (audit technique indépendant du 28 août 2026 appliqué : note de normativité ajoutée §1). Le contrat décrit la cible ; la matrice des outils est une photographie documentaire datée du 28 août 2026.

## 1. RoleDefinitionRevision

Une révision de définition de Rôle est immuable et appartient à un `PublishedContractBundle` versionné.

| Champ | Obligatoire | Invariant |
|---|---:|---|
| `role_id` | Oui | Identité stable et unique dans le bundle. |
| `revision` ou `content_hash` | Oui | Identifie exactement le contenu exécuté. |
| `mandate` | Oui | Ne confère aucune autorité implicite. |
| `product_write` | Oui | `none`, `tests_only` ou `scoped`; `scoped` doit préciser le périmètre. |
| `authoritative_governance_write` | Oui | `none` ou liste fermée de commandes du noyau ; aucune écriture libre de fichiers. |
| `non_authoritative_signal_write` | Oui | `none` ou liste de commandes médiées, par exemple `record_observation`. |
| `capability_policy` | Oui | Décrit fichiers, commandes, réseau et outils externes sans syntaxe propre à un outil. |
| `approval_policy` | Oui | Les actions humaines obligatoires ne peuvent être assouplies par l’Adaptateur. |
| `procedure_refs` | Oui | Chaque référence doit exister dans le même bundle. |
| `external_tools` | Non | Absence = aucun accès déclaré. |
| `model_preference` | Non | Valeur explicite ou héritage. |
| `isolation_requirement` | Non | Une exigence non satisfaisable produit une erreur de compatibilité. |

Cette structure remplace le champ binaire « Capacité d’écriture ». Un Rôle en lecture seule sur le produit peut demander l’enregistrement d’un signal par un port du noyau sans recevoir de capacité générale d’écriture de fichiers.

> **Note de normativité (ajoutée après audit indépendant)** : la table ci-dessus est **conceptuelle**. Le format de fil (wire format) normatif pour `RoleDefinitionRevision` — noms de champs exacts, imbrication — est exclusivement celui du Document 12 §2.2 (`writes.product.level`, `writes.authoritative_governance_commands`, `writes.non_authoritative_signal_commands`, `capabilities`, `isolation`). Un implémenteur ne doit pas instancier `product_write`, `authoritative_governance_write`, `non_authoritative_signal_write`, `capability_policy` ou `isolation_requirement` comme noms de champs JSON : ce sont des désignations pédagogiques pour ce document, pas des identifiants de schéma.

## 2. ProcedureRevision

| Champ | Obligatoire |
|---|---:|
| `procedure_id`, `revision` ou `content_hash` | Oui |
| `intent` | Oui |
| `required_inputs` | Oui |
| `steps` agnostiques de l’outil | Oui |
| `required_outputs` | Oui |
| `invariants` | Oui |
| `invocation_mode` (`discoverable` ou `explicit_only`) | Oui |

Une Procédure ne doit pas exiger une écriture ou un outil absent des capacités du Rôle qui la référence.

## 3. Matrice de traduction datée

| Contrat | Cursor observé/documenté | Claude Code documenté | Codex documenté |
|---|---|---|---|
| Identité/mandat | `name`, `description` dans le frontmatter | identifiant et `description` de subagent | champ `name` et instructions de custom agent |
| Écriture/capacité | `readonly` par agent ; `permissions.json` et `cli.json` au niveau projet ; sandbox du produit | `tools`, `disallowedTools`, `permissionMode` | `sandbox_mode`, politique d’approbation et configuration de l’environnement |
| Procédures | skills du repo, associations surtout textuelles dans ce dépôt | champ `skills` par subagent | `skills.config` par agent |
| MCP | configuration Cursor | `mcpServers` | `mcp_servers` |
| Modèle | `model` | `model` | `model` |
| Isolation | orchestrée hors du frontmatter d’agent dans ce dépôt | `isolation` | dépend du runtime/sandbox ; aucune équivalence complète démontrée ici |
| Hooks | `.cursor/hooks.json` | hooks d’agent et de settings | hooks de cycle de vie documentés |

La présence d’une primitive portant le même nom ne garantit pas la même sémantique. La suite de conformité doit tester le comportement effectif.

### Grain Cursor résolu partiellement

Dans le dépôt actuel, Cursor ne fournit pas une primitive unique et uniforme par Rôle :

- `readonly` est par agent ;
- `.cursor/permissions.json` est une politique de workspace fusionnée avec d’autres couches et n’est pas une frontière de sécurité forte ;
- `.cursor/cli.json` règle séparément Read/Write/Shell pour le CLI ;
- sur Windows natif, le preflight signale l’indisponibilité de `workspace_readonly`.

L’Adaptateur Cursor doit donc compiler plusieurs mécanismes et refuser un Rôle si l’ensemble ne satisfait pas son contrat.

## 4. Obligations de tout Adaptateur

1. Résoudre un bundle et des révisions exactes.
2. Produire des artefacts natifs sans augmenter les capacités ou diminuer les approbations.
3. Séparer écriture produit, commande d’état autoritaire et signal non autoritaire.
4. Ne persister l’état du noyau qu’au travers de commandes validées.
5. Produire un rapport de compatibilité explicite pour toute capacité non traduisible.
6. Retourner l’identité de l’Adaptateur, du bundle, du Rôle et de la Procédure effectivement exécutés.
7. Ne pas dépendre d’un hook comme unique barrière de sécurité.

## 5. Limites

- Seul Cursor est observé dans ce dépôt ; Claude Code et Codex ne sont pas testés end-to-end.
- Les noms et possibilités des primitives externes évoluent et doivent être revérifiés avant implémentation.
- La stratégie exacte de médiation des signaux en lecture seule reste à concevoir pour Cursor.

## Sources

`.cursor/agents/`, `.cursor/hooks.json`, `.cursor/permissions.json`, `.cursor/cli.json`, `scripts/ai-team/preflight.py`, documentations officielles Cursor, Claude Code et Codex consultées le 28 août 2026.
