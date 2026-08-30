# Guide opérateur

Commandes et flux pour un dépôt cible **sans lire le code source** du framework.

## Prérequis

```bash
python --version   # ≥ 3.10
pip install -r requirements.txt
```

Depuis la racine du **dépôt framework** (ou une copie extraite), toutes les commandes ci-dessous utilisent `tools/install.py`.

## Installation fraîche

Installe les composants gérés, initialise le profil projet et écrit `installation-record.json` **en dernier**.

```bash
python tools/install.py \
  --target /chemin/vers/mon-projet \
  --project-id mon-projet \
  --project-name "Mon Projet"
```

Effets principaux :

- Copie `.ai-team/`, `.cursor/` (via compilateur adaptateur), `scripts/`, `docs/product/`, `docs/operator/`, `AGENTS.md`, `requirements.txt`.
- Initialise `active_adapter_id: cursor` dans `.ai-team/project-profile.yaml` si absent.
- Compile `.cursor/` depuis le bundle publié et les templates adaptateur.

## Mise à jour transactionnelle

```bash
python tools/install.py --target /chemin/vers/mon-projet --update
```

Étapes (automatiques) :

1. Migration manifeste v1 → `installation-record.json` v2 si nécessaire.
2. Vérification de compatibilité de version.
3. Snapshot manifesté pour rollback.
4. Copie des fichiers gérés obsolètes ou modifiés par le framework.
5. Migrations d'acceptance et validation post-copie.
6. Écriture des manifestes v2 **après** validation réussie.

### Options utiles

| Option | Effet |
|---|---|
| `--dry-run` | Affiche le plan sans modifier le disque |
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
python scripts/ai-team/feedback.py export --detail-level structured
```

Les wrappers traduisent les arguments legacy vers le Command Gateway (message `DEPRECATED` sur stderr).

## Fichiers project-owned (jamais écrasés)

Exemples : `.ai-team/project-profile.yaml`, `.ai-team/state/*`, `.ai-team/work-units/*`, `.ai-team/events/*`, `.ai-team/evidence/*`, observations, rétrospectives.

Toute modification locale sur un fichier **managed** non project-owned peut produire un conflit explicite avec backup — voir Document 14 DI-006.

## Vérifier l'adaptateur actif

```bash
grep active_adapter_id .ai-team/project-profile.yaml
# attendu en 0.5.0 : cursor
```

La version du noyau installé est dans `.ai-team/installation-record.json` (`core.version`).
