# Configuration GitHub requise

Réglages du dépôt **source** du framework (fabrication) lui-même — pas un guide à
livrer aux projets clients. Pour la politique Git normative des projets où le
framework a été installé, voir [`client-git-policy.md`](../adopter-guide/client-git-policy.md).

Les hooks locaux ne remplacent pas les protections serveur. Un administrateur du dépôt
doit appliquer les réglages suivants, puis joindre une capture ou un export de règles à la
preuve de clôture de `WU-GIT-GOVERNANCE`.

## Règle de branche `main`

- exiger une pull request avant fusion ;
- exiger la résolution des conversations ;
- invalider les approbations devenues obsolètes ;
- exiger les checks `git-policy`, `tests` et `governance-validation` ;
- exiger que la branche soit à jour avant fusion ;
- bloquer force-push et suppression ;
- restreindre les pushes directs ;
- ne permettre aucun bypass silencieux, y compris administrateur ;
- conserver uniquement la stratégie merge commit ; désactiver squash et rebase merge.

Une approbation est exigée lorsqu'un second reviewer responsable est disponible. Tant que
le dépôt reste mono-mainteneur, le contrôle automatisé `governance-validation` est obligatoire
et l'acceptation humaine reste enregistrée dans `.ai-team/`.

## Règle de tags `v*`

- bloquer mise à jour et suppression ;
- réserver la création au parcours de release autorisé ;
- n'accepter que des tags annotés et signés (GPG ou SSH — vérifiés par `check_git_policy.py --tag`) ;
- exécuter le workflow sur le tag avant publication des artefacts.

Création locale typique :

```bash
git tag -s v0.7.1 -m "Release 0.7.1"
python scripts/ai-team/check_git_policy.py --tag v0.7.1
git push origin v0.7.1
```

## Correctifs patch et branches de maintenance

| Objectif | Branche | Tag résultant |
|---|---|---|
| Hotfix urgent | `hotfix/WU-<ID>-<slug>` depuis le dernier tag stable | `vX.Y.Z` patch suivant |
| Ligne `0.7.x` maintenue | `release/0.7` (pas `release/0.7.0`) | `v0.7.1`, `v0.7.2`, … |

Voir [`VERSIONING.md`](../../VERSIONING.md) pour le détail normatif.

Les tags historiques `v0.4.0` et `v0.6.0` sont conservés tels quels. La nouvelle règle
s'applique à toute création future et ne justifie pas leur déplacement.

## Réglages du dépôt

- branche par défaut : `main` ;
- merge commits : activés ;
- squash merge et rebase merge : désactivés ;
- **suppression automatique des branches après fusion : activée** (Settings → General → Pull Requests → *Automatically delete head branches*) ;
- GitHub Actions limité aux permissions minimales, `contents: read` par défaut (sauf workflow de nettoyage ci-dessous).

La vérification se fait avec un compte administrateur dans **Settings → Rules → Rulesets**
et **Settings → General → Pull Requests**. Un contrôle trimestriel compare les réglages
effectifs à ce document.

## Nettoyage automatique des branches fusionnées

Trois niveaux complémentaires — vous ne devriez plus avoir à supprimer manuellement les branches `wu/*`, `ai-run/*`, `integration/*` ou `hotfix/*` déjà fusionnées :

| Mécanisme | Quand | Action |
|---|---|---|
| **Réglage GitHub** | À chaque merge de PR | Supprime la branche head si activé dans les paramètres du dépôt |
| **Workflow `prune-merged-branches.yml`** | PR fusionnée | Supprime la branche head si elle correspond aux préfixes gouvernés (secours si le réglage GitHub est oublié) |
| **`workflow_dispatch`** | Manuel / backlog | Actions → *Prune merged branches* → `dry_run: false` pour purger toutes les branches distantes déjà mergées dans `main` |
| **Script local** | Secours | `python scripts/ai-team/prune_merged_branches.py` (dry-run) puis `--apply` |

Branches **jamais** supprimées automatiquement : `main`, `release/*` (maintenance active), branches hors préfixes gouvernés, branches fork.

Pour le backlog actuel (branches déjà mergées avant cette automatisation) :

1. GitHub → Actions → **Prune merged branches** → Run workflow → `dry_run: false`, ou
2. `python scripts/ai-team/prune_merged_branches.py --apply`
