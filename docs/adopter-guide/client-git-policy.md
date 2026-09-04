# Politique Git — projets installés

Normatif pour les projets où le framework a été installé
(`repository_kind: existing_or_greenfield_project`). Complète la Constitution,
notamment `.ai-team/constitution/95-git-release-policy.yaml`.

Pour la **fabrication du framework** sur ce dépôt source, voir
[`VERSIONING.md`](../../VERSIONING.md) et [`AGENTS.md`](../../AGENTS.md).

## Modèle trunk-based

`main` est la branche de référence publiable et doit rester vérifiée.

## Branches

| Usage | Format | Base | Durée de vie |
|---|---|---|---|
| Work Unit | `wu/WU-<ID>-<slug>` | `main` ou branche d'intégration autorisée | Jusqu'à fusion |
| Exécution automatisée | `ai-run/<RUN-ID>/<WU-ID>` | SHA de base du Run | Jusqu'à clôture du Run |
| Intégration multi-WU | `integration/<RUN-ID>` | `main` | Jusqu'à revalidation et fusion |
| Correctif urgent | `hotfix/WU-<ID>-<slug>` | dernière version supportée | Jusqu'à fusion et release corrective |
| Maintenance | `release/<major>.<minor>` | tag stable concerné | Ligne officiellement supportée |

Toute autre convention doit être approuvée et enregistrée avant utilisation.

## Commits

```text
type(WU-ID): description concise
type(WU-ID)!: changement incompatible
```

Types autorisés : `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`,
`ci`, `chore`, `revert`, `style` et `wip`. Un commit `wip` ne constitue jamais
une preuve vérifiée.

Un commit évalué par QA, revue, sécurité ou audit n'est ni amendé ni rebasé.
Toute correction produit un nouveau commit et invalide les preuves touchées.

## Pull requests et fusion

- Aucun push direct sur `main`.
- Toute fusion passe par une pull request reliée à une Work Unit.
- Tous les contrôles obligatoires portent sur le SHA candidat puis sur le SHA de fusion.
- Merge commit (`--no-ff`). Squash et rebase-merge interdits.
- Les approbations obsolètes sont invalidées après modification du candidat.
- Force-push, suppression de `main` et contournement silencieux des règles sont interdits.

## Correctifs urgents

| Situation | Branche | Base |
|---|---|---|
| Correctif urgent depuis `main` courant | `hotfix/WU-<ID>-<slug>` | tag ou commit de la dernière release stable |
| Correctif sur ligne `0.7.x` déjà sortie | `release/0.7` | tag `v0.7.0` (ou dernier patch) |
| Nouvelle capacité sur `main` | `wu/WU-<ID>-<slug>` | `main` |

Une branche `release/<major>.<minor>` porte un minor (`0.7`), pas un patch complet
(`0.7.0` est refusé par la politique de nommage).
