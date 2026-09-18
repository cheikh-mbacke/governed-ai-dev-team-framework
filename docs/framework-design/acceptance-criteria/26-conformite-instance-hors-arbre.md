# Document 26 — Conformité : gouvernance Instance hors-arbre

**Statut** : version 1.0 — critères d’acceptation du Document 25. Un scénario
n’est **attendu et observé** qu’après la phase indiquée ; avant cela il est
`expected_but_not_demonstrated`.

Les IDs `INS-AC-*` tracent `INS-F-*` et `INS-ADR-*` du Document 25.

## Standalone (dès Phase 0, non régressif)

### INS-AC-001 — Install in-tree inchangée

`tools/install.py --target <dépôt produit>` pose `.ai-team/` dans ce dépôt.
Compile, WU, preuves à un SHA, G3/G4 se comportent comme en 0.7.x.

### INS-AC-002 — Dépôt source refusé

Installer ou enregistrer un Ensemble sur `repository_kind: framework_source`
échoue sans écriture d’état client.

## Instance et catalogue (Phases 1–3)

### INS-AC-003 — Instance sans code produit

Install sur un répertoire vide : runtime + constitution + `catalog.yaml`
vide ou sans Ensemble. Aucun membre requis.

### INS-AC-004 — Enregistrer Ensemble et Membres

`RegisterEnsemble` puis deux `RegisterMember` avec des Git locaux distincts
persisté sous `.ai-team/ensembles/<id>/`. `catalog.yaml` liste l’Ensemble et
ses membres. Un `path` non-Git ou égal à l’instance est rejeté en hors-arbre.

### INS-AC-005 — Un Project State par Ensemble

Deux Ensembles ont des phases indépendantes : G1 boutique n’impose pas
`awaiting_g1_approval` à l’intranet.

### INS-AC-006 — Composition immuable

`PinComposition` crée `CR-*` avec une carte SHA 40 hex. Une seconde écriture
du même id échoue (create-exclusive).

## Isolation d’exécution (Phase 2)

### INS-AC-007 — Une exécution, un Git

Une WU `member_id: frontend` qui écrit un fichier du backend (path absolu,
`..`, ou glob hors membre) est rejetée **avant** commit durable.

### INS-AC-008 — Worktree sous l’instance

Le worktree d’exécution d’une WU membre est créé sous le `.ai-team/` de
l’instance et checkout le Git du membre, pas un clone du Git d’instance.

## Exclusive governance (Phase 4)

### INS-AC-009 — Lien mince

Après `RegisterMember`, le checkout membre contient `member-link.json` et un
pointeur `AGENTS.md`. `--update` de l’instance n’écrase pas le code produit.

### INS-AC-010 — Cycle refusé depuis le membre

`/compile-project`, `gov.py` client et skills de cycle lancés avec cwd =
membre retournent un échec explicite indiquant le chemin d’instance.

### INS-AC-011 — Assessment multi-membres

Un constat `blocking` non résolu sur **un** membre produit `no_go` pour
l’Ensemble. L’assessment ne mute aucun arbre membre.

## Compile et preuves (Phases 5–6)

### INS-AC-012 — WU étiquetées

La compile d’un Ensemble à front+back produit des WU portant `member_id` et
au moins une WU d’intégration sans write produit.

### INS-AC-013 — G3 sans composition

G3 (ou enregistrement de release candidate) sur un Ensemble à ≥ 2 membres
sans `composition_id` courant est rejeté.

### INS-AC-014 — SHA membre divergent

Si le HEAD d’un membre ≠ SHA piné, une preuve `kind: composition` existante
est invalide ; un e2e / G4 sur cette composition est rejeté jusqu’à nouveau
pin et re-vérification.

### INS-AC-015 — Standalone sans composition

Un Ensemble à 1 membre (in-tree) accepte encore `code_revision` string / SHA
unique pour G3.

## Adaptateur (Phase 7)

### INS-AC-016 — Cwd membre

Une `ExecutionRequest` de WU membre a `execution_workspace` = root (ou
worktree) du membre. L’Adaptateur n’utilise pas le root d’instance comme
arbre produit.

### INS-AC-017 — Workspace Ensemble actif

L’Adaptateur Cursor émet un fichier workspace listant l’instance et les
paths des membres de l’Ensemble **actif** seulement.

## Migration (Phase 8)

### INS-AC-018 — Opt-in

`--update` 0.7.x → 0.8.0 sans commande de migration laisse l’install
in-tree standalone. La commande de migration hors-arbre snapshot, déplace
l’état autoritaire vers l’instance, pose le lien mince, et se rollback.

## Hors critères 0.8.0

Pas de scénario : découverte automatique de siblings, SSH, Session Cloud,
commit atomique multi-Git, parité runtime Claude Code hors-arbre.
