# Politique de versionnement (hors Git)

Guide opérateur complémentaire à [`VERSIONING.md`](../../VERSIONING.md) et au Document 12. Décrit **quand** et **comment** monter chaque axe de version, et comment lire la matrice de compatibilité Distribution.

## Axes de version

| Axe | Fichier / emplacement | Cycle | Rôle |
|---|---|---|---|
| **Version produit** | `pyproject.toml` (canonique), `.fabric/framework-version.json` (source), `.ai-team/installation-record.json` → `core.version` (installé) | SemVer `MAJOR.MINOR.PATCH` | Release globale du framework |
| **Adaptateur livré** | `adapters/cursor/manifest.json` → `adapter_version` | **Identique à la version produit** pour l’adaptateur Cursor livré avec le framework | Capacités et plages supportées |
| **Protocole noyau↔adaptateur** | `manifest.json` → `protocol_versions` | Indépendant ; bump **majeur** si champ supprimé/renommé ou sémantique changée | Compatibilité SPI |
| **Bundle de contrats** | `distribution/payload/.ai-team/contracts/bundles/<version>/manifest.json` (source), `.ai-team/contracts/bundles/<version>/manifest.json` (installé) → `bundle_version` | SemVer ; répertoire **immuable** une fois publié | Snapshot rôles + procédures |
| **Révision rôle / procédure** | `roles/*.json`, `procedures/*.json` → `revision` | SemVer par artefact | Changement local au mandate ou aux steps |
| **Constitution** | `distribution/payload/.ai-team/constitution/constitution.yaml` (source), `.ai-team/constitution/constitution.yaml` (installé) → `version` | SemVer ; gelée en mid-cycle | Politiques d’ingénierie |
| **Schémas persistés** | `revision` (agrégats mutables v2), `schema_version` (installation record, manifestes) | Entier ou migration nommée | Évolution des formats de données |

Avant `1.0.0`, une rupture de compatibilité produit peut porter sur `MINOR` (voir `VERSIONING.md`).

## Règle adaptateur livré

Pour tout adaptateur **livré dans le dépôt** avec une release produit :

- `adapter_version` **doit être identique** à la version produit ;
- `installation-record.json` recopie cette valeur dans `adapters[].version` ;
- la matrice `distribution/installer/version_policy.py` est la source normative des plages `bundle_version_range` et `protocol_versions`.

Un futur adaptateur tiers pourra avoir son propre cycle ; il devra alors déclarer explicitement sa plage dans la matrice de release.

## Quand monter quoi

### Version produit (`pyproject.toml`)

| Changement | Bump |
|---|---|
| Correction rétrocompatible, pas de nouveau contrat | `PATCH` |
| Nouvelle capacité rétrocompatible (commande additive, migration auto) | `MINOR` |
| Rupture de compatibilité install/update ou suppression de capacité | `MAJOR` (ou `MINOR` avant `1.0.0`) |

Après bump : `python scripts/ai-team/sync_source_manifest.py`, mettre à jour `CHANGELOG.md`, `README.md`, `adapters/cursor/manifest.json` (`adapter_version`), ajouter/mettre à jour l’entrée dans `RELEASE_MATRIX`, puis :

```bash
python scripts/ai-team/check_release_matrix.py
```

### Bundle (`bundle_version`)

| Changement | Action |
|---|---|
| Texte de mandate, step ou capacité d’un rôle/procédure | Bump `revision` de l’artefact concerné ; republier un **nouveau** répertoire `bundles/<nouvelle_version>/` |
| Ajout de rôle/procédure (additif) | Bump **minor** du bundle |
| Suppression, renommage ou sémantique incompatible | Bump **major** du bundle ; adapter `bundle_version_range` dans le manifeste adaptateur et la matrice |

Ne jamais modifier un répertoire `bundles/<version>/` déjà publié : créer une nouvelle version et mettre à jour `active-bundle.json`.

### Protocole (`protocol_version`)

| Changement | Bump |
|---|---|
| Champ optionnel additif dans RuntimeResult / ExecutionRequest | Même protocole ou minor documenté |
| Champ supprimé, renommé ou sémantique incompatible | Nouveau `protocol_version` (ex. `2.0`) ; entrée parallèle dans `protocol_versions` pendant la transition |

### Constitution

Bump SemVer + analyse d’impact. En phase d’exécution mid-cycle : `--force-constitution-update` uniquement avec autorisation humaine ; événement `CONTRACT_CHANGE` enregistré.

## Matrice de compatibilité Distribution

Définie dans `distribution/installer/version_policy.py` → `RELEASE_MATRIX`.

Pour chaque version produit, la matrice fixe :

- `update_from` : versions installées acceptées en entrée d’une `--update` ;
- `adapters.<id>` : `adapter_version`, `bundle_version_range`, `protocol_versions` ;
- `data_schema_minimums` : niveaux minimaux de schéma requis pour lire les données projet ;
- `min_constitution_version` : Constitution minimale supportée.

L’installateur **refuse** :

- une version produit absente de la matrice ;
- un chemin d’update non listé dans `update_from` ;
- une **rétrogradation** produit (`DOWNGRADE_NOT_SUPPORTED`).

## Schémas de données — minimums par release

| Release produit | Installation record | Agrégats mutables | Bundle manifest |
|---|---|---|---|
| `0.7.0` | `schema_version` ≥ 3 | champs v2 (`revision`, timestamps) | `schema_version` 1 |

Une rétrogradation de **fichiers** (rollback installateur) ne convertit pas automatiquement les données vers un schéma antérieur. Voir [upgrading.md](upgrading.md).

## Fichiers synchronisés avec la version produit

La politique livrée est définie dans
`distribution/payload/.ai-team/constitution/95-git-release-policy.yaml`. Pour le
dépôt source, les fichiers synchronisés sont :

- `.fabric/framework-version.json`
- `adapters/cursor/manifest.json` (`adapter_version`)

## Vérifications automatiques

```bash
python scripts/ai-team/check_release_matrix.py
python scripts/ai-team/validate.py
python -m pytest tests/distribution/test_version_alignment.py tests/distribution/test_version_policy.py tests/contracts/test_semver.py -q
```

`check_release_matrix.py` échoue si `pyproject.toml` n’a pas d’entrée **courante** dans `RELEASE_MATRIX` (version absente, matrice en avance/retard, ou `update_from` incomplet).

`validate.py` (dépôt `framework_source`) inclut la même vérification avec l’alignement `framework-version.json` ↔ descriptor adaptateur.

## Références

- [`VERSIONING.md`](../../VERSIONING.md) — SemVer produit et séquence de release
- [`upgrading.md`](upgrading.md) — migrations installées
- [`deprecations.md`](deprecations.md) — remplacements et échéances
- Document 12 — contrats noyau ↔ adaptateur
