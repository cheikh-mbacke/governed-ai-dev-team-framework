# Upgrading — `0.4.x` → `0.5.0`

Guide de migration pour les projets installés avec l'ancien manifeste `framework-version.json` (v1).

## Avant de commencer

1. **Commit ou stash** de tout travail en cours — l'update refuse un dépôt Git sale par défaut.
2. Lire [deprecations.md](deprecations.md).
3. Sauvegarder manuellement `.ai-team/` si la politique projet l'exige (l'installateur crée aussi un snapshot).

## Versions supportées

La mise à jour accepte les installations depuis : `0.1.0`, `0.2.0`, `0.3.0`, `0.4.0`, `0.5.0` (idempotente).

Une version non listée est **refusée avant toute copie** (DI-009).

## Dry-run obligatoire (recommandé)

```bash
python tools/install.py --target . --update --dry-run
```

Vérifiez :

- fichiers obsolètes détectés par propriétaire ;
- migrations d'acceptance listées ;
- changement éventuel de Constitution ;
- absence de chemins non classables bloquants.

## Migration manifeste v1 → v2

| v1 (legacy) | v2 (cible) |
|---|---|
| `.ai-team/framework-version.json` | `.ai-team/installation-record.json` |
| liste plate `managed_files` | `managed_files` classés par propriétaire (`core`, `adapter:cursor`, `distribution`, `project`) |
| pas d'`active_adapter_id` | `active_adapter_id` requis (défaut `cursor` à l'install) |

Comportement :

- Chaque chemin legacy est classé ; un chemin **non classable bloque** la migration (DI-007).
- L'ancien manifeste est copié dans `.ai-team/migration-backups/<horodatage>/`.
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

1. Confirmer `.ai-team/installation-record.json` (`schema_version: 2`).
2. Confirmer `active_adapter_id` dans `.ai-team/project-profile.yaml`.
3. Vérifier que `.cursor/` a été recompilé depuis le bundle v1.
4. Relancer la suite de tests projet si applicable.

## Constitution en mid-cycle

Par défaut, une nouvelle version de Constitution est **gelée** si le projet est en phase d'exécution mid-cycle. Pour forcer :

```bash
python tools/install.py --target . --update --force-constitution-update
```

Un événement `CONTRACT_CHANGE` est enregistré ; les Work Units déjà gateées sous l'ancienne Constitution ne sont **pas** re-validées rétroactivement.

## Échec et rollback

Si la validation post-copie échoue (DI-010) :

1. L'installateur restaure le snapshot ;
2. Le manifeste legacy ou v2 précédent est rétabli ;
3. Un diagnostic est produit ; le backup sous `migration-backups/` est conservé.

## Non rétrogradable

- Les objets créés sous schémas v2 (horodatages `revision`, champs gateway) **ne sont pas** automatiquement convertis vers v1.
- Un rollback logiciel restaure les **fichiers** ; une migration inverse de données explicite est requise pour une rétrogradation déclarée sûre.

## Limites résiduelles

- Qualification Cursor réelle : voir Document 14 niveaux L3/L4.
- Tests L4 indisponibles ne comptent pas comme succès pour une release candidate.
