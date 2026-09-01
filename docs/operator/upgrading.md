# Upgrading — `0.4.x` → `0.7.0`

Guide de migration pour les projets installés avec les manifestes legacy ou le layout 0.6.x.

## Avant de commencer

1. **Commit ou stash** de tout travail en cours — l'update refuse un dépôt Git sale par défaut.
2. Lire [deprecations.md](deprecations.md).
3. Sauvegarder manuellement `.ai-team/` si la politique projet l'exige (l'installateur crée aussi un snapshot).

## Versions supportées

La mise à jour accepte les installations depuis : `0.1.0` … `0.6.0`, et idempotemment `0.7.0`.

Une version non listée est **refusée avant toute copie** (DI-009).

## Dry-run obligatoire (recommandé)

```bash
python tools/install.py --target . --update --dry-run
```

Vérifiez :

- fichiers obsolètes détectés par propriétaire ;
- migrations d'acceptance listées ;
- changement éventuel de Constitution ;
- absence de chemins non classables bloquants ;
- **aucune écriture** (y compris migration v1→v2 sur manifeste legacy).

## Migration layout `0.6.x` → `0.7.0`

| Ancien chemin (0.6.x) | Nouveau chemin (0.7.0) |
|---|---|
| `src/governed_ai/**` | `.ai-team/runtime/governed_ai/**` |
| `adapters/cursor/**` | `.ai-team/runtime/governed_ai/adapters/cursor/**` |
| `requirements.txt` (racine) | `.ai-team/requirements.txt` |
| `docs/product/`, `docs/operator/` | **non installés** dans le projet cible |
| `README.md` (racine framework) | **non installé** |

Chemins déplacés automatiquement lors de l'update depuis 0.6.x. Fichiers ambigus à la racine (`README.md`, `requirements.txt`, `AGENTS.md`) **ne sont jamais déplacés/supprimés automatiquement** : un événement `DECISION_REQUEST` est émis pour revue humaine.

## Migration manifeste v1 → v2 → v3

| v1 (legacy) | v2 | v3 (cible 0.7.0) |
|---|---|---|
| `.ai-team/framework-version.json` | `.ai-team/installation-record.json` | idem, `schema_version: 3` |
| liste plate `managed_files` | classés par propriétaire | + `installed_sha256` par chemin |

Comportement :

- Chaque chemin legacy est classé ; un chemin **non classable bloque** la migration (DI-007).
- L'ancien manifeste est copié dans `.ai-team/migration-backups/`.
- Aucun `managed_file` ne doit disparaître silencieusement (DI-003).

## Procédure de mise à jour

```bash
# 1. Dry-run
python tools/install.py --target . --update --dry-run

# 2. Update réelle
python tools/install.py --target . --update

# 3. Validation
python scripts/ai-team/validate.py
```

## Après migration

1. Confirmer `.ai-team/installation-record.json` (`schema_version: 3`).
2. Confirmer `.ai-team/runtime/governed_ai/` présent.
3. Installer les deps : `pip install -r .ai-team/requirements.txt`.
4. Confirmer `active_adapter_id` dans `.ai-team/project-profile.yaml`.
5. Vérifier que `.cursor/` a été recompilé depuis le bundle actif.
6. Traiter les événements `DECISION_REQUEST` de revue forensic si présents.
7. Relancer la suite de tests projet si applicable.

## Constitution en mid-cycle

Par défaut, une nouvelle version de Constitution est **gelée** si le projet est en phase d'exécution mid-cycle. Pour forcer :

```bash
python tools/install.py --target . --update --force-constitution-update
```

Un événement `CONTRACT_CHANGE` est enregistré ; les Work Units déjà gateées sous l'ancienne Constitution ne sont **pas** re-validées rétroactivement.

## Échec et rollback

Si la validation post-copie échoue (DI-010) :

1. L'installateur restaure le snapshot ;
2. Le manifeste précédent est rétabli ;
3. Un diagnostic est produit ; le backup sous `migration-backups/` est conservé.

L'installation fraîche utilise le même mécanisme de rollback transactionnel.

## Non rétrogradable

- Les objets créés sous schémas v2/v3 (horodatages `revision`, champs gateway, hashes) **ne sont pas** automatiquement convertis vers v1.
- Un rollback logiciel restaure les **fichiers** ; une migration inverse de données explicite est requise pour une rétrogradation déclarée sûre.

### Minimums de schéma par version produit installée

| Version produit | Installation record | Agrégats mutables (Work Unit, etc.) | Bundle manifest |
|---|---|---|---|
| `0.7.0` | `schema_version` ≥ 3 | champs v2 (`revision`, `created_at`, `updated_at`) | `schema_version` 1 |

Détail et règles de bump : [versioning-policy.md](versioning-policy.md).

## Limites résiduelles

- Qualification Cursor réelle : voir Document 14 niveaux L3/L4.
- Tests L4 indisponibles ne comptent pas comme succès pour une release candidate.

