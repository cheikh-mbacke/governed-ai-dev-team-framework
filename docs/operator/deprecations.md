# Dépréciations et échéances

Éléments remplacés par la refonte `0.5.0`. Phase 6 nettoyage (**WU-P6-CLEANUP**) : voir [Recherche consommateurs](#recherche-consommateurs-wu-p6-cleanup) et [Supprimé en 0.6.0](#supprimé-en-060).

## Recherche consommateurs (WU-P6-CLEANUP)

Recherche `rg` sur le dépôt (scripts, tests, docs, `.ai-team/`, `tools/`) avant suppression :

| Fichier cible | Consommateurs runtime restants | Décision |
|---|---|---|
| `scripts/ai-team/record_gate.py` | Aucun import/script ; tests golden et `test_legacy_wrappers` invoquaient le CLI directement ; handler `RecordGateDecision` via `gov.py` | **Supprimé** — remplacer par `gov.py command` |
| `scripts/ai-team/common.py` | Aucun `import common` dans `scripts/` ; logique dans `governed_ai.core` | **Supprimé** |
| `scripts/ai-team/feedback_common.py` | Aucun import ; `validate.py` exigeait seulement sa présence ; logique dans `governed_ai.feedback` | **Supprimé** |
| `.cursor/` vs `adapters/cursor/templates/.cursor/` | Parité shadow compile vérifiée (0 divergence bloquante) ; listes de fichiers identiques | **Conservé** — `.cursor/` est la sortie installée ; templates = source compilateur |

## Supprimé en 0.6.0

## Formats et fichiers

| Élément | Remplacement | Échéance indicative |
|---|---|---|
| `.ai-team/framework-version.json` (v1) | `.ai-team/installation-record.json` (v3) | Migré automatiquement à la première `--update` ; fichier legacy préservé en backup |
| Écritures directes YAML d'état par scripts | Command Gateway (`gov.py`) | `0.6.0` |

## Scripts CLI

| Script | Statut | Remplacement |
|---|---|---|
| ~~`scripts/ai-team/record_gate.py`~~ | **Supprimé `0.6.0`** | `gov.py command` avec enveloppe `RecordGateDecision` |
| ~~`scripts/ai-team/common.py`~~, ~~`feedback_common.py`~~ | **Supprimés `0.6.0`** | `governed_ai.core` / `governed_ai.feedback` |
| `scripts/ai-team/feedback.py` (écritures) | **Wrapper de transition** | Command Gateway pour record/export ; stdout legacy conservé |
| `scripts/ai-team/migrate.py` | Wrapper acceptance | Appelé par l'installateur ; ne pas invoquer manuellement sauf debug |

Messages `DEPRECATED` émis sur stderr par les wrappers legacy.

## Comportements

| Ancien comportement | Nouveau comportement |
|---|---|
| `adapter_id: cursor` en dur dans le noyau | `active_adapter_id` lu depuis `.ai-team/project-profile.yaml` |
| Sidecar compilateur dans le bundle agnostique | `adapters/cursor/compiler-notes.yaml` (hors manifeste) |
| Références `.cursor/skills/...` dans la Constitution | Formulations agnostiques (procédures / skills adaptateur) |

## Non livré (hors périmètre 0.5.0)

- Adaptateurs **Claude Code** et **Codex CLI** — étude de portabilité du contrat uniquement ; **aucun stub fonctionnel**.
- Session Cloud, API publique Internet, synchronisation mobile.

## Limites à ne pas présenter comme garanties

- Parité Cursor sur toutes plateformes sans qualification Document 14 L4.
- Rétrogradation automatique des données schéma v2 vers v1.
- Sécurité ou qualité du modèle IA sous-jacent.
- `workspace_readonly` sur Windows natif dans tous les scénarios.

Signaler toute friction via `python scripts/ai-team/feedback.py record`.
