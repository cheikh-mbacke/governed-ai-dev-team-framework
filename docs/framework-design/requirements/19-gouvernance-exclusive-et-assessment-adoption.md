# Document 19 — Gouvernance exclusive et assessment d’adoption

**Statut** : version 1.2 — exigence normative. La commande `tools/assess.py` et le garde-fou `--assessment-report` sur l’install fraîche sont **livrés** ; la catégorie `baseline` (matière humaine / inventaire as-built brownfield) est **livrée** ; la couverture automatique des conflits `authority` reste partielle (saisie / confirmation humaine via `--resolutions`).

Les termes **DOIT**, **NE DOIT PAS**, **DEVRAIT** et **PEUT** expriment respectivement une obligation, une interdiction, une recommandation forte et une option.

## 1. Problème

Installer le framework dans un dépôt déjà en cours sans inventaire préalable des conflits produit deux échecs fréquents :

1. **adoption partielle** — coexistence d’autorités (process Git historique, agents Cursor maison, bots hors Gateway) et gouvernance framework, d’où preuves ambiguës et contournements ;
2. **surprise post-mutation** — collisions et remodelages découverts seulement après écriture sur disque.

La détection actuelle de collisions à l’installation (chemins) et les outils `preflight` / `diagnose` (après installation) ne couvrent pas l’inventaire des conflits de gouvernance **avant** engagement.

## 2. Principes

1. **Gouvernance exclusive** — une fois l’adoption engagée, le framework est la seule autorité de gouvernance du développement assisté par IA sur le dépôt cible. Tout conflit durable avec cette autorité DOIT être éliminé, remappé vers un mécanisme gouverné, ou faire l’objet d’une dérogation humaine explicite prévue par la Constitution. Une demi-gouvernance N’EST PAS un mode supporté.
2. **Consentement éclairé avant mutation** — justement parce que le coût d’alignement est élevé et non diluable, le framework DOIT rendre ce coût visible **avant** toute opération mutante d’installation. Le diagnostic ne crée pas un mode hybride ; il force une décision humaine lucide : *aligner et adopter*, ou *ne pas adopter*.
3. **Assessment ≠ Gate G0** — l’Assessment d’adoption précède l’installation. G0 suppose déjà le framework installé et une baseline gouvernée. L’Assessment est une **porte d’entrée humaine**, pas une gate du cycle projet.
4. **Baseline brownfield avant compile** — sur un dépôt déjà développé, l’Assessment DOIT rendre visible que la matière humaine autoritaire et l’inventaire as-built (écarts, hors-scope, nettoyage) sont des **engagements post-install pré-compile**, distincts des collisions d’artefacts. Le dépôt n’est jamais une autorité produit.

## 3. Formulation normative

> Le framework revendique une gouvernance exclusive. L’adopter engage l’équipe à aligner outils, process et artefacts sur cette gouvernance. Le coût est volontairement élevé et non diluable. Pour que cet engagement soit responsable, le framework fournit un diagnostic pré-adoption qui révèle tous les conflits avant toute opération mutante. Refuser de résoudre un conflit bloquant, c’est refuser l’adoption — pas inventer un mode hybride.

## 4. Séquence d’adoption

```text
[Assessment] → [Décision] → [Install] → [/reconcile-project] → [G0 / compile] → …
 lecture seule   humain      mutation     project-owned (humain)           gouvernance
```

| Étape | Écriture disque cible | Sortie |
|---|---|---|
| Assessment | Aucune (hors éventuel rapport exporté hors arbre managé, si demandé explicitement) | Rapport d’assessment (GO / NO-GO + backlog, y compris `baseline`) |
| Décision d’adoption | Artefact project-owned ou enregistrement humain hors install | Acceptation explicite des principes §2 et du backlog résolu |
| Install fraîche | Oui | `installation-record.json` v3 |
| `/reconcile-project` | Project-owned (`docs/product/`, décisions, source-registry, rapport de réconciliation) | Intention cohérente + convergence approuvée + baseline empreintée avant compile |
| G0 / compile et suite | Via Command Gateway / skills | Plan dérivé ; gaps code↔intention signalés, jamais réécriture de l’intention |

## 5. Exigences — Assessment d’adoption

| ID | Exigence |
|---|---|
| ADO-F-001 | Une commande d’assessment (nom cible : `assess` / équivalent Distribution) DOIT pouvoir s’exécuter sur un chemin `--target` **sans** installation préalable du framework dans cette cible. |
| ADO-F-002 | L’assessment NE DOIT PAS modifier l’arbre cible (pas de copie payload, pas d’écrasement `.cursor/`, pas d’écriture `.ai-team/` managé). |
| ADO-F-003 | L’assessment DOIT produire un rapport machine-lisible et un résumé humain classant chaque constat par catégorie §6 et par sévérité §7. |
| ADO-F-004 | Le rapport DOIT conclure par un verdict `go`, `go_with_backlog` ou `no_go`. |
| ADO-F-005 | Un verdict `no_go` DOIT être émis s’il reste au moins un constat `blocking` non résolu (statut autre que `eliminate`, `remap` ou `waive` consigné). |
| ADO-F-006 | L’installateur fraîche DEVRAIT refuser d’écrire lorsque aucun Assessment Decision compatible n’est fourni ou référencé, sauf contournement humain explicite documenté (équivalent esprit `--force`, avec avertissement). La politique exacte de lien Assessment → Install est tranchée à l’implémentation ; le principe « pas d’engagement aveugle » reste obligatoire. |
| ADO-F-007 | L’assessment NE DOIT PAS être confondu avec `preflight.py` (pré-Run) ni `diagnose.py` (diagnostic post-install). |
| ADO-F-008 | Un mode hybride « gouvernance framework + autorité concurrente non résolue » NE DOIT PAS être proposé comme option d’assessment ni d’installation. |
| ADO-F-009 | L’assessment DOIT exposer une catégorie `baseline` qui signale l’engagement post-install pré-compile : matière humaine suffisante (Definition of Ready) et, si du code applicatif est détecté, inventaire as-built (écarts de conformité, hors-scope, nettoyage → Work Units explicites). |
| ADO-F-010 | L’assessment NE DOIT PAS traiter le contenu du dépôt comme autorité produit ; en cas de code existant sans matière produit détectée, un constat `warning` DOIT figurer au backlog (`go_with_backlog` tant que non résolu). |

## 6. Catégories de constats

| Code | Catégorie | Objet |
|---|---|---|
| `engagement` | Décision d’engagement | Acceptation des principes §2 ; autorités humaines à nommer |
| `authority` | Autorité / process | Git, CI, branch protection, releases, autres orchestrateurs d’agents |
| `artifact` | Artefacts concurrents | `.cursor/` custom, `AGENTS.md` concurrent, scripts/bots hors Gateway |
| `prerequisite` | Prérequis techniques | Python, Git, Cursor, droits, dépendances |
| `baseline` | Baseline produit / as-built | Matière humaine avant compile ; inventaire des écarts code↔intention, hors-scope, nettoyage |
| `remodel` | Remodelage | Actions concrètes `eliminate` / `remap` / `waive` / `defer_blocks_adoption` |

Chaque constat DOIT porter au minimum : `id`, `category`, `severity`, `summary`, `evidence` (chemin, règle ou observation), `resolution_options`, `resolution_status` (si connu).

## 7. Sévérités

| Sévérité | Effet sur le verdict |
|---|---|
| `blocking` | Empêche `go` tant que non résolu (`eliminate`, `remap` ou `waive` autorisé) |
| `warning` | N’empêche pas seul un `go_with_backlog` ; DOIT apparaître dans le backlog |
| `info` | Signalement sans effet sur le verdict |

## 8. Résolutions autorisées

| Statut | Signification |
|---|---|
| `eliminate` | Le conflit est retiré du dépôt / du process |
| `remap` | Le comportement est recâblé vers un mécanisme gouverné (Gateway, gate, politique Git framework…) |
| `waive` | Dérogation humaine explicite, seulement si la Constitution ou une Decision Request le permet ; tracée |
| `defer_blocks_adoption` | Report volontaire = adoption refusée ou reportée (`no_go`) |
| `unresolved` | Détecté, pas encore tranché |

`waive` sans trace humaine NE DOIT PAS être accepté comme résolution d’un `blocking`.

## 9. Hors périmètre de ce document

- Implémentation détaillée du parseur de politiques Git distantes ou de chaque CI vendeur.
- Mode de gouvernance progressive ou « lite ».
- Remplacement de G0–G4.
- Assessment d’un dépôt `repository_kind: framework_source` (fabrication) : hors cible adoptant.

## 10. Limites

- La couverture automatisable des conflits `authority` reste partielle ; les constats non détectables automatiquement DOIVENT pouvoir être saisis ou confirmés par un opérateur humain via `--resolutions` / la Décision d’adoption.
- La catégorie `baseline` détecte des racines de code et de docs par heuristique ; elle ne remplace pas G0 ni un audit exhaustif du dépôt. L’inventaire as-built détaillé reste humain (puis Work Units après compile).
- Ce document ne modifie pas les schémas runtime Gouvernance existants.

## Références

- Document 9 — Distribution / Installation
- Document 11 — Architecture cible (séquence install)
- Document 20 — Critères de conformité assessment d’adoption
- Document 21 — Réconciliation pré-compilation
- Guide adoptant — [adoption-assessment.md](../../adopter-guide/adoption-assessment.md)
