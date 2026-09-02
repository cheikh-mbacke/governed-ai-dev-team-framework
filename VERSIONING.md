# Politique Git et versionnement

Ce document est normatif pour **ce dépôt source** (`repository_kind:
framework_source`). Il complète la Constitution livrée aux projets installés.

## Fabrication (ce dépôt)

| Élément | Convention |
|---|---|
| Branches | `renov/<slug>`, `fix/<slug>`, `feat/<slug>`, `docs/<slug>`, `chore/<slug>`, `release/<major>.<minor>` |
| Commits | Conventional Commits : `feat: …`, `fix: …`, `docs: …` |
| PR | Vers `main`, tests et `validate.py` verts |

Workflow détaillé : [`AGENTS.md`](AGENTS.md).

## Projets installés

Politique Git client (branches `wu/…`, commits `type(WU-ID): …`) :
[`docs/operator/client-git-policy.md`](docs/operator/client-git-policy.md).

## Version produit

Le framework suit Semantic Versioning `MAJOR.MINOR.PATCH` :

- `MAJOR` : rupture de compatibilité après `1.0.0` ;
- `MINOR` : fonctionnalité rétrocompatible ;
- `PATCH` : correction rétrocompatible.

`pyproject.toml` est la source canonique. `.fabric/framework-version.json` et
`adapters/cursor/manifest.json` → `adapter_version` doivent rester alignés (voir
[`docs/operator/versioning-policy.md`](docs/operator/versioning-policy.md)).

## Releases et tags

1. Préparer version, changelog, migrations et rollback ;
2. Tests, lint, `validate.py`, `check_release_matrix.py` ;
3. Fusion merge commit dans `main` ;
4. Tag annoté et signé `vMAJOR.MINOR.PATCH` sur le SHA de merge ;
5. GitHub Release et artefacts depuis le tag.

Le changelog doit contenir une entrée datée avant validation du tag. Placeholders
(`Non publiée`, `Unreleased`) refusés par `check_git_policy.py --tag`.

Les fichiers texte sont versionnés en LF ; seuls les scripts Windows `.cmd`/`.bat`
sont en CRLF.

## Maintenance et urgences

Lignes maintenues déclarées dans le changelog et la doc opérateur. Hotfix : mêmes
contrôles, traçabilité et autorité humaine conservés.

## Rupture historique 0.4.x

Voir [`docs/operator/history-cutover-0.4.md`](docs/operator/history-cutover-0.4.md).
