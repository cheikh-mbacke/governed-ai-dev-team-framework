# Assessment d’adoption (pré-installation)

Guide opérateur pour la **porte d’entrée** du framework : inventaire des conflits **avant** toute installation. Normatif côté conception : Documents 19 et 20 sous `docs/framework-design/`.

## Principe

Le framework revendique une **gouvernance exclusive**. L’adopter, c’est accepter d’aligner outils, process et artefacts — pas de mode hybride. Le coût est volontairement élevé. Pour que cet engagement soit responsable, un **assessment** (lecture seule) révèle les conflits avant toute mutation.

```text
Assessment (lecture seule) → Décision → Install → /reconcile-project → G0 / compile → …
```

- **Assessment** ≠ `preflight.py` (avant un Run) ≠ `diagnose.py` (après install).
- **Assessment** ≠ gate **G0** (G0 suppose le framework déjà installé).
- Sur un **brownfield**, l’assessment expose aussi la catégorie `baseline` : engagement à produire la matière humaine et un inventaire as-built **avant** la première compile — le dépôt n’est pas une autorité produit.

## Quand l’exécuter

- Avant la **première** installation sur un dépôt existant (brownfield) ou neuf.
- Avant de décider d’adopter, lorsque l’équipe veut connaître le prix d’alignement.
- Pas comme substitut à une gouvernance partielle : un backlog `blocking` non résolu signifie **ne pas installer**, pas « installer quand même en mode soft ».

## État de livraison

| Élément | État |
|---|---|
| Principes et catégories (Documents 19–20) | Spécifiés |
| Guide et checklist adoptant | Le présent document |
| Commande slash Cursor (depuis le dépôt framework) | **Livrée** — `/assess-adoption <cible>` (lecture seule) |
| Commande CLI | **Livrée** — `tools/assess.py` (lecture seule) |
| Lien Assessment → install | **Livré** — `--assessment-report` obligatoire sauf `--skip-assessment-gate` / `GOVERNED_AI_SKIP_ASSESSMENT_GATE=1` |

## Commande

Depuis Cursor ouvert sur le dépôt framework, la façade opérateur est :

```text
/assess-adoption /chemin/vers/mon-projet
```

Elle exécute la CLI ci-dessous sans modifier la cible. Les résolutions et le
chemin d'un éventuel rapport doivent rester des choix humains explicites. Cette
commande est volontairement dans l'overlay source `.cursor/` : elle doit être
disponible **avant** l'installation, contrairement aux commandes du cycle client.

Depuis le dépôt framework :

```bash
python tools/assess.py --target /chemin/vers/mon-projet
python tools/assess.py --target /chemin/vers/mon-projet --json
python tools/assess.py --target /chemin/vers/mon-projet --json --report-file /tmp/assessment.json
```

Appliquer des résolutions humaines (après décision d’équipe) :

```bash
python tools/assess.py --target /chemin/vers/mon-projet \
  --resolutions resolutions.json \
  --json --report-file /tmp/assessment.json
```

Exemple `resolutions.json` :

```json
{
  "findings": {
    "engagement.exclusive_governance": { "resolution_status": "remap" },
    "engagement.human_authorities": { "resolution_status": "remap" },
    "baseline.human_material_before_compile": { "resolution_status": "remap" },
    "baseline.as_built_inventory": { "resolution_status": "remap" },
    "baseline.product_material_gap": { "resolution_status": "remap" },
    "artifact.cursor_tree": { "resolution_status": "eliminate" },
    "artifact.cursor_cli_json": {
      "resolution_status": "waive",
      "waiver_authorization_id": "AUTH-ADOPT-001"
    }
  }
}
```

Codes de sortie : `0` = `go` ou `go_with_backlog` ; `2` = `no_go` ; `1` = erreur.

Install ensuite :

```bash
python tools/install.py --target /chemin/vers/mon-projet \
  --project-id <id> --project-name "<nom>" \
  --assessment-report /tmp/assessment.json
```

Sans rapport `go`/`go_with_backlog`, l’install fraîche refuse. Contournement explicite uniquement :

```bash
python tools/install.py ... --skip-assessment-gate
```

## Grille manuelle (complément humain)

La CLI couvre les détections automatiques ; les constats `authority` restent partiels. Compléter / confirmer :

### A — Engagement (`engagement`)

- [ ] L’équipe accepte la gouvernance exclusive (pas d’autorité agent/process concurrente non résolue) — typiquement `engagement.exclusive_governance` → `remap`.
- [ ] Autorités humaines désignées — `engagement.human_authorities` → `remap`.

### B — Autorité / process (`authority`) — souvent `blocking`

- [ ] Conventions de branches compatibles avec la politique client (`wu/…`, pas de push direct sur `main`, etc.) ou plan de remap.
- [ ] Merge : squash / rebase-merge / force-push sur `main` identifiés et traités.
- [ ] CI / branch protection : écarts inventoriés.
- [ ] Autres orchestrateurs d’agents ou bots qui mutent l’état du dépôt : éliminer ou remapper vers le Command Gateway.

### C — Artefacts (`artifact`) — souvent `blocking` si `.cursor/` riche

- [ ] `.cursor/` existant (agents, rules, hooks, permissions, cli) : collision connue avec l’adaptateur ; plan eliminate/remap avant `--force`.
- [ ] `AGENTS.md` / instructions IDE concurrentes : fusion acceptable (marqueurs) ou conflit de fond à trancher.
- [ ] Scripts locaux qui écrivent un « état projet » hors Gateway.

### D — Prérequis (`prerequisite`)

- [ ] Python ≥ 3.10 disponible pour l’installateur et le runtime.
- [ ] Dépôt Git (recommandé pour updates transactionnelles).
- [ ] Cursor comme outil d’exécution prévu (seul adaptateur livré en 0.7.x).
- [ ] Chemins produit / commandes de build-test identifiables pour le futur `project-profile.yaml`.

### E — Baseline produit / as-built (`baseline`) — critique en brownfield

Ces constats sont en général des `warning` : l’install peut passer en `go_with_backlog`, mais **ne compilez pas** tant qu’ils ne sont pas tenus.

- [ ] `baseline.human_material_before_compile` → `remap` : matière produit autoritaire (souvent `docs/product/`) suffisante pour le premier périmètre, puis source-registry.
- [ ] Si code applicatif détecté (`src/`, `app/`, …) : `baseline.as_built_inventory` → `remap` : inventaire écrit des écarts (non-conforme à l’intention, hors-scope, nettoyage) destinés à des WU ou décisions.
- [ ] Si code sans `docs/product/` : `baseline.product_material_gap` → `remap` (écrire la matière) ou `waive` tracé si une autre source autoritaire est déjà décidée.
- [ ] Rappeler : le code existant est **réalité observée**, pas permission de réécrire l’intention.

### F — Backlog de remodelage (`remodel`)

- [ ] Chaque `blocking` a une résolution autre que `unresolved` / `defer_blocks_adoption`, **ou** l’adoption est reportée (`no_go`).
- [ ] Les `waive` ont une trace humaine (qui, quoi, pourquoi).
- [ ] Les `warning` `baseline` ouverts restent dans le backlog post-install jusqu’à matière + inventaire.

## Verdict

| Verdict | Condition | Action |
|---|---|---|
| `go` | Aucun `blocking` ouvert ; pas de warning critique laissé sans backlog | Procéder à l’install |
| `go_with_backlog` | Aucun `blocking` ouvert ; warnings acceptés avec plan | Install + suivre le backlog |
| `no_go` | Au moins un `blocking` non résolu ou reporté | **Ne pas installer** |

## Après un `go` / `go_with_backlog`

1. Enregistrer la Décision d’adoption (qui a approuvé, date, lien vers le rapport JSON).
2. Installer avec le rapport :

   ```bash
   python tools/install.py --target /chemin/vers/mon-projet \
     --project-id <id> --project-name "<nom>" \
     --assessment-report /chemin/vers/assessment.json
   ```

3. **Avant** G0 / `/compile-project` (surtout brownfield) :
   - compléter `project-profile.yaml` et `source-registry.yaml` ;
   - produire ou aligner la matière humaine autoritaire pour le premier périmètre ;
   - rédiger l’inventaire as-built (écarts, hors-scope, nettoyage) si du code existait déjà ;
   - résoudre / suivre les warnings `baseline` du backlog.
   - invoquer `/reconcile-project` jusqu’à une baseline `ready` et vérifiée.
4. Enchaîner la [checklist adoptant](adopter-checklist.md) (G0…).

Un `go_with_backlog` dû uniquement à `baseline` signifie : **installer oui, compiler non** tant que matière + inventaire ne sont pas tenus.

## Ce qui n’est pas négociable

- Pas de « on garde notre process agent en parallèle et on verra ».
- Pas d’install pour « essayer un peu la gouvernance » sur le dépôt de production sans décision.
- Un `--force` sur collision `.cursor/` **sans** assessment préalable reste un risque conscient : l’assessment existe précisément pour le rendre explicite avant coup.

## Références

- [adopter-checklist.md](adopter-checklist.md)
- [operator-guide.md](operator-guide.md)
- [client-git-policy.md](client-git-policy.md)
- [security-model.md](security-model.md)
- Document 19 — `docs/framework-design/requirements/19-gouvernance-exclusive-et-assessment-adoption.md`
- Document 20 — `docs/framework-design/acceptance-criteria/20-conformite-assessment-adoption.md`
