# Document 25 — Gouvernance hors-arbre : Instance, Ensemble, Membre

**Statut** : version 1.0 — conception et plan de mise en œuvre. Les termes
**DOIT**, **NE DOIT PAS**, **DEVRAIT** et **PEUT** expriment respectivement une
obligation, une interdiction, une recommandation forte et une option.

Ce document ne décrit **pas** le dépôt source du framework
(`repository_kind: framework_source`). Il décrit l’**instance installée chez
l’adoptant**, dans son propre répertoire, qui agit sur les dépôts produit
**depuis un autre répertoire de la même machine**.

Hors périmètre (inchangé) : Session Cloud (ADR-008), SSH, API distante, agents
cloud, console hébergée. « À distance » signifie uniquement **hors de l’arbre
produit**, pas le réseau.

## 1. Problème

Le noyau gouverne aujourd’hui **un** `Workspace.root` Git. L’installateur pose
`.ai-team/` **dans** le dépôt produit. Front, back et backoffice en dépôts
distincts deviennent N cycles indépendants (N profils, N Project States, N SHA
de preuve). Une preuve « end-to-end » ou une gate G3/G4 produit n’a pas
d’agrégat.

Le mode déjà supporté — dossiers `frontend/` et `backend/` **dans le même
Git** — reste valide. Il n’est pas le sujet de ce document.

## 2. Décisions structurantes

| ID | Décision | Conséquence |
|---|---|---|
| INS-ADR-001 | L’instance du framework a son **propre répertoire Git**, distinct des dépôts produit. | Cursor et le Gateway s’ouvrent sur l’instance. |
| INS-ADR-002 | L’instance agit sur les membres par **chemins locaux** (même machine). | Pas de transport réseau pour piloter un membre. |
| INS-ADR-003 | Le dépôt **source** du framework n’est jamais une instance. | `tools/install.py` refuse `framework_source` (déjà vrai) ; aucune commande client n’y enregistre un ensemble. |
| INS-ADR-004 | Une install runtime = une instance ; N **Ensembles** ; chaque Ensemble a M **Membres**. | Un seul `Project State` pour toute l’org est interdit. |
| INS-ADR-005 | L’état autoritaire (`.ai-team/` gates, WU, preuves, catalogue) vit **uniquement** dans l’instance. | Les membres n’ont pas de second cycle. |
| INS-ADR-006 | Une exécution produit n’écrit **qu’un** Git membre. | Feature transversale = graphe de WU + WU d’intégration sans write produit. |
| INS-ADR-007 | Preuve **produit** (e2e, visuelle, G3, G4) = **révision de composition** `{ membre → SHA }`. | Un SHA isolé ne suffit plus dès qu’un Ensemble a ≥ 2 membres. |
| INS-ADR-008 | L’install **in-tree** actuelle reste le mode `standalone` : 1 Ensemble implicite, 1 Membre = le root installé. | Pas de rupture obligatoire pour les projets 0.7.x. |
| INS-ADR-009 | Exclusive governance hors-arbre : **lien mince** sur chaque membre (`member-link` + `AGENTS.md`). | Ouvrir seul le front et lancer `/compile-project` refuse. |
| INS-ADR-010 | `catalog.yaml` est un **index** (modèle de lecture). | Il ne fusionne pas les phases des Ensembles. |
| INS-ADR-011 | La composition est un artefact Gateway, pas une obligation submodules. | Submodules possibles comme checkout, jamais comme source de vérité. |
| INS-ADR-012 | L’Adaptateur génère un workspace multi-root pour **l’Ensemble actif** seulement. | Pas tous les produits de l’org montés d’un coup. |

## 3. Langage

| Terme | Définition |
|---|---|
| **Instance** | Répertoire Git où le framework est installé. Identité `instance_id`. Contient constitution, runtime, catalogue, Ensembles. |
| **Catalogue** | Index project-owned des Ensembles gouvernés (`catalog.yaml`). |
| **Ensemble** | Un produit gouverné (gates, compile, WU, composition). Identité stable (ex. `boutique`). A son propre Project State. |
| **Membre** | Dépôt Git de code déclaré (`backend`, `frontend`, `backoffice`) avec `path` local obligatoire et `origin` optionnel. |
| **Révision de composition** | Jeton immuable `CR-*` : carte membre → commit SHA 40 hex, créée par commande. |
| **Lien mince** | Fichier non autoritaire sur le membre : `ensemble_id`, `member_id`, chemin d’instance. |
| **Standalone** | Ensemble à un membre dont le root **est** le root d’instance (comportement 0.7.x). |
| **Hors-arbre** | Ensemble dont les membres ont un root **différent** du root d’instance. |

`project.id` actuel DEVRAIT, en standalone, rester l’identité de l’Ensemble
implicite. En hors-arbre, `project.id` au profil d’instance identifie
l’instance ; chaque Ensemble a le sien.

## 4. Disposition cible

```text
~/acme-ai-team/                         ← Instance (Git)
  .ai-team/
    installation-record.json            ← une install
    project-profile.yaml                ← identité d’instance + adapter
    catalog.yaml                        ← vue centrale
    constitution/ schemas/ contracts/ runtime/
    ensembles/
      boutique/
        project-profile.yaml            ← produit
        sources/ state/ work-units/ evidence/
        members.yaml
        compositions/CR-*.yaml
        reconciliation/
      intranet/
        …
  docs/product/boutique/                ← intention du produit
  .cursor/                              ← compilé une fois
  acme-ai-team.code-workspace           ← généré, Ensemble actif

~/code/boutique-api/                    ← Membre (autre Git)
  .ai-team/member-link.json             ← lien mince seulement
  AGENTS.md                             ← pointeur vers l’instance
~/code/boutique-web/
~/code/boutique-admin/
```

Les worktrees d’exécution DEVRAIENT vivre sous
`.ai-team/worktrees/<ensemble>/<run>/<wu>/` **dans l’instance**, branchés sur
le Git du membre (le code actuel branche déjà un worktree hors de l’arbre
candidat).

## 5. Invariants

1. `Workspace.discover` depuis l’instance trouve l’instance. Depuis un membre,
   il trouve le `member-link` et **NE DOIT PAS** traiter le membre comme
   projet standalone.
2. `resolve_under_root` pour une WU hors-arbre utilise le **root du membre**,
   pas l’instance. Traversée vers un autre membre = erreur.
3. Verrou transactionnel : un verrou **par Ensemble** (pas un verrou global
   d’instance qui sérialise l’intranet et la boutique).
4. `code_revision` discriminé :
   - `kind: git_commit` + `sha` — preuve locale d’un membre (ou standalone) ;
   - `kind: composition` + `composition_id` + carte SHA — preuve produit.
5. « End-to-end verified » avec ≥ 2 membres **exige** `kind: composition` et
   l’observation réelle des processus concernés sur **ces** SHA.
6. Enregistrement des membres : déclaration humaine, jamais découverte
   automatique d’un sibling `../frontend`.
7. Un membre déclaré DOIT exister comme dépôt Git local au moment de
   l’enregistrement et de chaque exécution qui le cible.

## 6. Exigences fonctionnelles

| ID | Exigence |
|---|---|
| INS-F-001 | L’install fraîche PEUT cibler un répertoire vide (instance) sans code produit. |
| INS-F-002 | Le mode standalone (install dans un dépôt déjà produit) DOIT rester fonctionnel sans déclaration d’Ensemble. |
| INS-F-003 | Une commande DOIT enregistrer un Ensemble sous l’instance (identité, docs produit, profil). |
| INS-F-004 | Une commande DOIT enregistrer un Membre (`id`, `kind`, `path` local, `origin` optionnel, `source_roots`, `commands`). |
| INS-F-005 | `path` d’un membre DOIT être un répertoire Git distinct de l’instance en mode hors-arbre. |
| INS-F-006 | Une WU hors-arbre DOIT porter `member_id` ; une exécution sans `member_id` est rejetée dès que l’Ensemble a ≥ 2 membres. |
| INS-F-007 | Une commande DOIT figer une révision de composition à partir des HEAD déclarés (ou SHA explicites) de tous les membres. |
| INS-F-008 | G3 et G4 d’un Ensemble à ≥ 2 membres DOIVENT référencer une composition courante, pas un SHA unique. |
| INS-F-009 | `/compile-project` et le cycle client lancés depuis un membre DOIVENT refuser et indiquer le chemin d’instance. |
| INS-F-010 | L’assessment d’un Ensemble hors-arbre DOIT porter sur l’instance **et** chaque membre déclaré, avec un seul verdict. |
| INS-F-011 | `catalog.yaml` DOIT lister chaque Ensemble (id, phase, membres, composition courante si posée) sans recopier le Project State. |
| INS-F-012 | Le Context Package d’une WU membre PEUT inclure des artefacts du hub (`docs/product/`, contrats) en lecture ; il NE DOIT PAS autoriser l’écriture hors membre. |
| INS-F-013 | Une WU d’intégration (`member_id` absent ou `kind: integration`) NE DOIT PAS écrire de code produit dans un membre. |
| INS-F-014 | Migration opt-in : un install 0.7.x in-tree DOIT pouvoir rester standalone ; un passage hors-arbre est une commande explicite, pas un `--update` silencieux. |

## 7. Plan de mise en œuvre

Version produit visée : **0.8.0** (capacité additive avant `1.0.0` ; standalone
inchangé). Bundle de contrats : minor si procédures/rôles seulement enrichis.
Schémas persistés : nouveaux fichiers + `code_revision` additif (l’ancien
champ string RESTE accepté en standalone = `git_commit`).

Aucune phase suivante ne commence tant que la sortie de la précédente n’est
pas verte (tests + `validate.py`).

### Phase 0 — Gel et caractérisation

**Travaux**

- Fixtures : projet `clean` standalone (déjà là) ; ajouter une fixture
  **instance vide** et une fixture **ensemble à 2 membres factices** (deux
  mini-Git temporaires dans les tests, pas un layout productif).
- Caractériser `Workspace.discover`, `resolve_under_root`, `head_sha`,
  `tools/install.py --target`, compile fencing, evidence `code_revision`.
- Interdire toute régression standalone.

**Sortie** : suite actuelle verte ; tests de caractérisation nommés
`test_standalone_*` qui devront rester verts jusqu’à 0.8.0.

### Phase 1 — Langage, schémas, modèle sans effet visible

**Travaux**

- Étendre Document 1 (langage) et Document 7 (agrégats) par référence à ce
  document ; ne pas dupliquer les définitions.
- Schémas payload :
  - `catalog.schema.json`
  - `ensemble-members.schema.json`
  - `composition-revision.schema.json`
  - `member-link.schema.json`
  - `work-unit.schema.json` : `member_id` optionnel
  - `evidence.schema.json` / champs WU : `code_revision` objet ou string
- `Workspace` : `instance_root`, `ensembles_root`, `active_ensemble_id`,
  résolution de membre. En standalone, `instance_root == member_root`.
- Aucune commande nouvelle exposée. Seeds standalone inchangés.

**Sortie** : `sync_source_manifest.py` + `validate.py` verts ; tests unitaires
de résolution standalone ≡ comportement 0.7.x.

### Phase 2 — Git et chemins par membre

**Travaux**

- `git_workspace.py` / execution gateway : `cwd` et `safe.directory` = root
  **membre** ; worktrees sous l’instance.
- `resolve_under_root(member_root, rel)` ; refuse d’écrire dans l’instance
  depuis une WU membre (sauf artefacts Gateway, hors scope agent).
- Orchestrateur : `execution_workspace` déjà présent — le remplir avec le
  root membre / worktree membre.

**Sortie** : tests d’isolation à 2 Git temporaires (write front n’altère pas
le back ; path escape inter-membres rejeté). Standalone identique.

### Phase 3 — Commandes Ensemble / Membre / Composition

**Travaux**

- Command Gateway : `RegisterEnsemble`, `RegisterMember`, `PinComposition`,
  éventuellement `SetActiveEnsemble` (Adaptateur / CLI).
- Écriture `catalog.yaml` comme projection post-commit (pas d’autorité
  parallèle).
- CLI : `python scripts/ai-team/gov.py` + éventuellement
  `scripts/ai-team/ensemble.py` wrapper.

**Sortie** : tests de commande (révisions, `CONFLICT`, path non-Git rejeté,
composition immuable).

### Phase 4 — Distribution, assessment, lien mince

**Travaux**

- `tools/install.py` : cible instance (répertoire sans code) **ou** in-tree
  (standalone). Pas de changement du garde-fou `framework_source`.
- Overlay membre : écrire `member-link.json` + bloc `AGENTS.md` lors de
  `RegisterMember` (project-owned, jamais écrasé par `--update` du runtime
  instance).
- `tools/assess.py` : `--instance` + `--member id=path` répété ; un verdict
  pour l’Ensemble ; `no_go` d’un membre bloque.
- Document 19 : gouvernance exclusive s’étend aux membres déclarés, pas
  seulement au `--target` d’install.

**Sortie** : install instance sur fixture vide ; assess 2 membres ; overlay
présent ; `--update` instance n’écrase pas les repos produit.

### Phase 5 — Réconciliation et compile par Ensemble

**Travaux**

- `/reconcile-project` et fingerprint : par Ensemble, inventaire **de chaque
  membre** ; baseline empreintée multi-arbres (carte path→digest par membre).
- `/compile-project` : WU étiquetées `member_id` ; graphe d’intégration ;
  intention dans `docs/product/<ensemble>/` de l’instance.
- Skills : garde « lancé depuis un membre → stop ».

**Sortie** : compile d’un Ensemble 2 membres produit au moins une WU par
membre concerné + dépendances ; compile depuis le checkout membre = échec.

### Phase 6 — Preuves produit et gates

**Travaux**

- G3/G4 / release candidate : exiger `composition_id` si `len(members) ≥ 2`.
- Design Authority / e2e : lancer N serveurs **sur la composition figée**
  (worktrees aux SHA pinés), pas « ce qui tourne en local ».
- Règle evidence : invalider la composition si un membre avance.

**Sortie** : tests G3 sans composition = rejeté ; e2e avec SHA front ≠ pin =
rejeté ; standalone G3 inchangé (SHA unique).

### Phase 7 — Adaptateur Cursor (et contrat SPI)

**Travaux**

- Compilateur : artefacts sous l’instance ; génération
  `*.code-workspace` Ensemble actif (hub + paths membres).
- Runtime : `project_dir` / cwd = membre de la WU (le SPI a déjà
  `execution_workspace`).
- Claude Code : **même contrat** ; pas de parité Cursor exigée dans la même
  PR, mais aucun champ SPI nommé Cursor.
- Document 12 : `ExecutionRequest` PEUT porter `member_id` +
  `member_root` (additif, protocole minor ou champ optionnel).

**Sortie** : tests compilateur (workspace JSON / chemins) ; test d’invocation
avec cwd membre. Conformité L3/L4 Cursor réel : Phase 7b, hors définition de
« code mergé ».

### Phase 8 — Guides adoptant et migration opt-in

**Travaux**

- `docs/adopter-guide/` : installer une instance, enregistrer un Ensemble,
  déclarer front/back/backoffice, ouvrir Cursor sur l’instance.
- Mettre à jour `docs/README.md` (carte physique instance vs membres).
- Commande de migration : in-tree 0.7 → instance hors-arbre (déplacer
  `.ai-team/` autoritaire, laisser lien mince). **Opt-in**, snapshot,
  rollback.
- `docs/framework-design/users-and-rules/01-langage-ubiquitaire.md` et
  Documents 7, 9, 11, 19 : amendements ponctuels (références à INS-ADR-*).

**Sortie** : guide opérateur ; test de migration aller/rollback sur fixture
legacy in-tree.

## 8. Ordre des branches de fabrication

Suivre `AGENTS.md` : branches courtes `renov/instance-p<n>-<slug>`, PR vers
`main`, Conventional Commits. Ne pas livrer les Phases 3–7 dans une seule PR.

Proposition de découpe PR :

1. Docs (ce document + index corpus) — **cette livraison**
2. Phase 0–1 (schémas + Workspace)
3. Phase 2 (git/paths)
4. Phase 3 (commandes)
5. Phase 4 (install/assess/lien)
6. Phase 5 (reconcile/compile)
7. Phase 6 (preuves/gates)
8. Phase 7 (adaptateur)
9. Phase 8 (guides + migration)

## 9. Hors périmètre de 0.8.0

- Découverte automatique de dépôts siblings.
- Transaction distribuée / commit atomique multi-Git.
- Flotte de microservices sans Ensemble déclaré.
- Hub dans un membre « principal » (le back propriétaire du produit).
- Pilotage SSH/cloud.
- Un Project State unique pour toute l’organisation.
- Obligation git submodules.
- Changer le dépôt source du framework en cadastre de produits clients.

## 10. Limites

- Les verrous restent filesystem local (Document 11 §11) ; membres sur NFS
  non garantis.
- Cursor multi-root dépend de l’outil ; si indisponible, l’opérateur ouvre
  l’instance et l’Adaptateur fixe le cwd membre (capacité déjà au SPI).
- La parité Claude Code hors-arbre n’est pas un critère de sortie 0.8.0 ;
  le contrat SPI l’est.
- Tant que la Phase 6 n’est pas livrée, un Ensemble ≥ 2 membres NE DOIT PAS
  être recommandé en production : le modèle serait descriptif sans preuve
  produit.

## Sources

Décisions issues du cadrage produit (instance hors-arbre, Ensemble, Membres,
composition, standalone conservé). Documents 1, 7, 11, 12, 13, 19, 21.
`src/governed_ai/core/workspace.py`, `git_workspace.py`,
`execution_gateway`, `tools/install.py`.
