# Politique Git et versionnement

Ce document est normatif pour ce dépôt. Il complète la Constitution d'ingénierie,
notamment `.ai-team/constitution/95-git-release-policy.yaml`.

## Modèle de développement

Le dépôt suit un modèle trunk-based gouverné. `main` est la seule branche de
référence publiable et doit rester dans un état vérifié.

Les changements sont réalisés sur des branches courtes :

| Usage | Format | Base | Durée de vie |
|---|---|---|---|
| Work Unit | `wu/WU-<ID>-<slug>` | `main` ou branche d'intégration autorisée | Jusqu'à fusion |
| Exécution automatisée | `ai-run/<RUN-ID>/<WU-ID>` | SHA de base du Run | Jusqu'à clôture du Run |
| Intégration multi-WU | `integration/<RUN-ID>` | `main` | Jusqu'à revalidation et fusion |
| Correctif urgent | `hotfix/WU-<ID>-<slug>` | dernière version supportée | Jusqu'à fusion et release corrective |
| Maintenance | `release/<major>.<minor>` | tag stable concerné | Seulement si la ligne est officiellement supportée |

Toute autre convention doit être approuvée et enregistrée avant utilisation.
Les branches fusionnées sont supprimées, sauf branche de maintenance active.

## Commits

Les commits non générés utilisent :

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
- La stratégie retenue est le merge commit (`--no-ff`). Squash et rebase-merge sont interdits.
- Les approbations obsolètes sont invalidées après toute modification du candidat.
- Une approbation indépendante est requise dès qu'un second reviewer responsable est disponible.
  En environnement mono-mainteneur, le check `governance-validation` tient lieu de contrôle
  temporaire et ne remplace pas l'acceptation humaine requise par la Constitution.
- Force-push, suppression de `main` et contournement silencieux des règles sont interdits.

## Version produit

Le framework suit Semantic Versioning sous la forme `MAJOR.MINOR.PATCH` :

- `MAJOR` : rupture de compatibilité après `1.0.0` ; avant `1.0.0`, rupture significative
  portée par l'incrément `MINOR` ;
- `MINOR` : fonctionnalité rétrocompatible ;
- `PATCH` : correction rétrocompatible sans nouvelle capacité contractuelle.

`pyproject.toml` est la source canonique de la version produit. La valeur de
`.ai-team/framework-version.json` doit être identique. Pour l’adaptateur Cursor livré,
`adapters/cursor/manifest.json` → `adapter_version` doit aussi être identique (voir
[`docs/operator/versioning-policy.md`](docs/operator/versioning-policy.md)).

Les versions de protocole, de Constitution, de bundle et d’Adaptateur ont leur propre
cycle documenté ; seul l’adaptateur **embarqué** suit la version produit. La matrice
`distribution/installer/version_policy.py` fixe les combinaisons supportées à l’update.

## Releases et tags

Une release stable suit cette séquence :

1. préparer la version, le changelog, les migrations, le rollback et le candidat de release ;
2. exécuter tests, lint, validation de gouvernance et contrôle de cohérence des versions ;
3. obtenir les revues, audits et gates applicables ;
4. fusionner par merge commit dans `main` et revalider ce SHA ;
5. créer un tag annoté et signé `vMAJOR.MINOR.PATCH` sur ce SHA exact ;
6. publier une GitHub Release et les artefacts à partir du tag, jamais d'un arbre local ;
7. enregistrer le SHA, les digests, les preuves et le plan de rollback.

Un tag `v*` est immuable : il n'est ni déplacé ni supprimé. Une erreur de release est
corrigée par une nouvelle version et documentée dans le changelog.

Les fichiers texte sont versionnés en LF pour garantir des hashes reproductibles ; seuls
les scripts Windows `.cmd` et `.bat` sont matérialisés en CRLF.

## Maintenance et urgences

Les lignes maintenues sont déclarées explicitement dans le changelog et la documentation
opérateur. Un hotfix suit les mêmes contrôles qu'une autre modification. Une procédure
d'urgence peut réduire les délais, jamais supprimer la traçabilité, la revalidation ou
l'autorité humaine de production.

## Rupture historique 0.4.x

La lignée conservée par `release/0.4.0` et `v0.4.0` est volontairement distincte du
`main` actuel. Cette décision et ses limites sont consignées dans
`docs/operator/history-cutover-0.4.md`. Les deux historiques doivent rester intacts.
