# Architecture — vue opérateur

Résumé opérationnel de l'architecture refondue (`0.5.0`). Pour le détail normatif, voir [`docs/product/architecture-and-constraints/11-architecture-cible.md`](../product/architecture-and-constraints/11-architecture-cible.md).

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
│ (Cursor en 0.5.0)            │   │ observations / export│
│ compilateur │ runtime        │   └──────────────────────┘
└───────────────┬──────────────┘
                │ artefacts natifs de l'outil
                ▼
             OUTIL D'EXÉCUTION

┌─────────────────────────────────────────────────────────┐
│ DISTRIBUTION                                            │
│ install │ migrate │ validate │ rollback │ record v2    │
└─────────────────────────────────────────────────────────┘
```

## Règles structurantes

1. **Source de vérité** — fichiers d'état transactionnels (YAML/JSON sous `.ai-team/`), pas le chat ni la sortie brute d'un agent.
2. **Mutations autoritaires** — uniquement via le **Command Gateway** (`scripts/ai-team/gov.py`). Les Adaptateurs ne modifient pas directement Work Units, Project State, décisions ou preuves.
3. **Bundle agnostique** — rôles et procédures versionnés sous `.ai-team/contracts/bundles/<version>/`. L'Adaptateur compile une révision exacte vers ses artefacts natifs (ex. `.cursor/` pour Cursor).
4. **Classification des fichiers** — chaque chemin géré appartient à `core`, `adapter:<id>`, `distribution` ou `project`. Les fichiers **project-owned** ne sont jamais écrasés par une mise à jour.
5. **Installation Record v2** — `.ai-team/installation-record.json` recense les fichiers gérés et l'`active_adapter_id`. Écrit **en dernier** après une install ou update réussie.

## Arborescence installée (extrait)

```text
.ai-team/
  constitution/          # géré par le noyau
  contracts/             # bundle publié + pointeur active-bundle.json
  state/                 # project-owned — gates, phase, WU
  work-units/            # project-owned
  installation-record.json
  project-profile.yaml   # project-owned — identité + active_adapter_id
.cursor/                 # géré par l'adaptateur actif (Cursor en 0.5.0)
scripts/ai-team/         # wrappers CLI vers le noyau
docs/product/            # docs produit normatives
docs/operator/           # ce guide
AGENTS.md
```

## Limites connues

- Seul l'**Adaptateur Cursor** est livré en `0.5.0`. Aucun Adaptateur Claude Code ou Codex n'est fourni.
- Le comportement d'un Cursor réel dépend de la version et de la plateforme ; qualification via Document 14 (niveaux L3/L4).
- Distribution ne dépend pas du noyau à l'exécution ; le noyau ne dépend pas de Distribution.
