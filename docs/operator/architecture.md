# Architecture — vue opérateur

Résumé opérationnel de l'architecture refondue (`0.7.0`). Pour le détail normatif, voir [`docs/product/architecture-and-constraints/11-architecture-cible.md`](../product/architecture-and-constraints/11-architecture-cible.md).

## Composants

```text
                    OPÉRATEUR HUMAIN
                         │ gates / consentement
                         ▼
┌─────────────────────────────────────────────────────────┐
│ NOYAU DE GOUVERNANCE (Core)                             │
│ Bundle de contrats │ Command Gateway │ Agrégats │ Store │
└───────────────┬───────────────────────────┬─────────────┘
                │ SPI Adaptateur            │ lectures
                ▼                           ▼
┌──────────────────────────────┐   ┌──────────────────────┐
│ ADAPTATEUR ACTIF             │   │ FEEDBACK             │
│ (Cursor en 0.7.0)            │   │ observations / export│
│ compilateur │ runtime        │   └──────────────────────┘
└───────────────┬──────────────┘
                │ artefacts natifs de l'outil
                ▼
             OUTIL D'EXÉCUTION

┌─────────────────────────────────────────────────────────┐
│ DISTRIBUTION                                            │
│ install │ migrate │ validate │ rollback │ record v3    │
└─────────────────────────────────────────────────────────┘
```

## Règles structurantes

1. **Source de vérité** — fichiers d'état transactionnels (YAML/JSON sous `.ai-team/`), pas le chat ni la sortie brute d'un agent.
2. **Mutations autoritaires** — uniquement via le **Command Gateway** (`scripts/ai-team/gov.py`). Les Adaptateurs ne modifient pas directement Work Units, Project State, décisions ou preuves.
3. **Bundle agnostique** — rôles et procédures versionnés sous `.ai-team/contracts/bundles/<version>/`. L'Adaptateur compile une révision exacte vers ses artefacts natifs (ex. `.cursor/` pour Cursor).
4. **Classification des fichiers** — chaque chemin géré appartient à `core`, `adapter:<id>`, `distribution` ou `project`. Les fichiers **project-owned** ne sont jamais écrasés par une mise à jour.
5. **Installation Record v3** — `.ai-team/installation-record.json` recense les fichiers gérés, leur propriétaire et un `installed_sha256` par fichier. Écrit **en dernier** après une install ou update réussie.

## Arborescence installée (extrait)

```text
.ai-team/
  constitution/                 # core-managed
  schemas/ contracts/           # core-managed
  runtime/governed_ai/          # core-managed runtime Python + adaptateur Cursor
  requirements.txt              # dépendances framework (PyYAML, jsonschema, …)
  state/ work-units/ …          # project-owned
  installation-record.json      # distribution-managed (schema v3)
.cursor/                        # adapter:cursor-managed (compilé)
scripts/ai-team/*.py            # CLI / wrappers core-managed
AGENTS.md                       # core-managed (bloc marqueurs si fusion)
```

Le runtime framework **n'est plus copié** à la racine sous `src/`, `adapters/` ou `docs/`. Les guides opérateur et la doc produit normative restent dans le dépôt framework, pas dans le projet cible.

## Limites connues

- Seul l'**Adaptateur Cursor** est livré en `0.7.0`. Aucun Adaptateur Claude Code ou Codex n'est fourni.
- Le comportement d'un Cursor réel dépend de la version et de la plateforme ; qualification via Document 14 (niveaux L3/L4).
- Distribution ne dépend pas du noyau à l'exécution ; le noyau ne dépend pas de Distribution.

## Dépôt framework vs projet installé

Le **dépôt source** (`repository_kind: framework_source`) n'est pas une cible `tools/install.py` :

| | Dépôt source (fabrication) | Projet installé |
|---|---|---|
| Ancre gouvernance | `.fabric/project-profile.yaml` | `.ai-team/project-profile.yaml` |
| Payload constitution/schemas | `distribution/payload/.ai-team/` | `.ai-team/` |
| Runtime Python | `src/governed_ai/` | `.ai-team/runtime/governed_ai/` |
| Adaptateur Cursor | `adapters/cursor/` | sous `.ai-team/runtime/…` |
| Manifeste de version | `.fabric/framework-version.json` (chemins **source**) | `.ai-team/installation-record.json` v3 |
| Doc opérateur / tests | présents | absents |
| Cycle client (WU, gates, `/compile-project`) | **absent** — pas de `.ai-team/` racine | actif |

Regénérer le manifeste source après modification du payload installable :

```bash
python scripts/ai-team/sync_source_manifest.py
python scripts/ai-team/validate.py
```

Ne pas créer ni conserver `.ai-team/installation-record.json` dans le dépôt source : ce fichier décrit une **installation réelle** et utilise des chemins cible (`.ai-team/runtime/…`).
