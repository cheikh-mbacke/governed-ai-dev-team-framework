# Guide opérateur

Commandes et flux pour un dépôt cible **sans lire le code source** du framework.

## Prérequis

Depuis le **dépôt framework** (pour lancer l'installateur) :

```bash
python --version   # ≥ 3.10
pip install -r requirements.txt
```

Dans un **projet cible installé**, les dépendances framework sont sous `.ai-team/requirements.txt` :

```bash
pip install -r .ai-team/requirements.txt
```

Depuis la racine du dépôt framework (ou une copie extraite), toutes les commandes d'installation ci-dessous utilisent `tools/install.py`.

## Installation fraîche

Installe les composants gérés, initialise le profil projet et écrit `installation-record.json` **en dernier**.

```bash
python tools/install.py \
  --target /chemin/vers/mon-projet \
  --project-id mon-projet \
  --project-name "Mon Projet"
```

Effets principaux (layout Document 11 §4) :

- Copie `.ai-team/` (constitution, schémas, contrats, templates), `.cursor/` (compilé), `scripts/ai-team/`, `AGENTS.md`.
- Copie le runtime Python sous `.ai-team/runtime/governed_ai/` et l'adaptateur Cursor sous `.ai-team/runtime/governed_ai/adapters/cursor/`.
- Copie les dépendances framework dans `.ai-team/requirements.txt` (plus à la racine du projet cible).
- **Ne copie pas** `README.md`, `docs/product/`, `docs/operator/` dans le projet cible.
- Détecte les collisions avec des répertoires projet existants (`src/`, `docs/`, …) **avant** toute écriture ; utilise `--force` pour outrepasser.
- Si `AGENTS.md` existe déjà, fusionne un bloc `<!-- governed-ai:start -->` … `<!-- governed-ai:end -->` sans écraser le reste.

## Mise à jour transactionnelle

```bash
python tools/install.py --target /chemin/vers/mon-projet --update
```

Étapes (automatiques) :

1. Plan de mise à jour (y compris détection de dérive via hash v3).
2. `--dry-run` : affiche le plan **sans aucune écriture** (y compris migration v1→v2).
3. Migration manifeste v1 → v2 si nécessaire (hors dry-run).
4. Relocalisation layout 0.6.x → 0.7.x si applicable.
5. Snapshot manifesté pour rollback.
6. Copie / fusion des fichiers gérés modifiés.
7. Migrations d'acceptance et validation post-copie.
8. Écriture des manifestes v3 **après** validation réussie.

### Options utiles

| Option | Effet |
|---|---|
| `--dry-run` | Affiche le plan sans modifier le disque |
| `--force` | Install fraîche : ignore les collisions de chemins projet |
| `--allow-dirty` | Autorise un dépôt Git sale (non recommandé) |
| `--skip-validation` | Ignore `validate.py` post-update (non recommandé) |
| `--force-constitution-update` | Active une nouvelle Constitution en mid-cycle (enregistre un CONTRACT_CHANGE) |

### Rollback manuel

En cas d'échec après snapshot, l'installateur restaure les fichiers et manifestes depuis le backup horodaté sous `.ai-team/migration-backups/`. Ne supprimez pas ce dossier tant qu'une mise à jour n'est pas confirmée stable.

## Validation

```bash
cd /chemin/vers/mon-projet
python scripts/ai-team/validate.py
```

Contrôle schémas, cohérence Project State, Work Units et installation record.

## Command Gateway (recommandé)

Soumettre une Command Envelope JSON :

```bash
python scripts/ai-team/gov.py command --input envelope.json
# ou stdin
cat envelope.json | python scripts/ai-team/gov.py command
```

Autres sous-commandes : `recover`, `query` — voir `python scripts/ai-team/gov.py --help`.

## Diagnostic et pré-vol

```bash
python scripts/ai-team/preflight.py    # checks avant session
python scripts/ai-team/diagnose.py     # rapport d'état projet
python scripts/ai-team/status.py       # résumé gates / WU
```

## Feedback et observations

```bash
python scripts/ai-team/feedback.py record --category tooling --symptom "..."
python scripts/ai-team/feedback.py export
python scripts/ai-team/feedback.py submit
```

Sous `telemetry.collection: consented_share` (défaut : installer = accepter),
l'export est **full** avec `project_id`, sans anonymisation ni `--authorization-id`.
`submit` pousse vers `telemetry.submit_url` / `GOVERNED_AI_FEEDBACK_SUBMIT_URL`,
sinon vers `.ai-team/metrics/outbox/`. En cas d'échec réseau, l'export reste
dans l'outbox ; `python scripts/ai-team/feedback.py flush-outbox` retente (chaque
`submit` drain aussi l'outbox). Ingest framework :
`scripts/ai-team/ingest_feedback.py`. Le choix de l'adoptant est d'utiliser le
framework ou non — pas un mode privacy intermédiaire.

Les wrappers traduisent les arguments legacy vers le Command Gateway (message `DEPRECATED` sur stderr).

## Fichiers project-owned (jamais écrasés)

Exemples : `.ai-team/project-profile.yaml`, `.ai-team/state/*`, `.ai-team/work-units/*`, `.ai-team/events/*`, `.ai-team/evidence/*`, observations, rétrospectives.

Toute modification locale sur un fichier **managed** non project-owned peut produire un conflit explicite (hash v3 ou backup) — voir Document 14 DI-006. Utilisez `--force` sur update pour écraser après revue.

## Vérifier l'adaptateur actif

```bash
grep active_adapter_id .ai-team/project-profile.yaml
# attendu en 0.7.0 : cursor
```

La version du noyau installé est dans `.ai-team/installation-record.json` (`core.version`, `schema_version: 3`).
