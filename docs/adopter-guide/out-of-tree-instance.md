# Instance hors-arbre

Guide opérateur pour installer une **instance** séparée des dépôts produit, enregistrer un **Ensemble**, déclarer des **Membres** (front / back / backoffice), et ouvrir Cursor sur l’instance (Document 25).

Le mode **standalone** 0.7.x (framework installé dans le dépôt produit) reste valide. Le passage hors-arbre est **opt-in** : `tools/install.py --update` ne le déclenche jamais (INS-AC-018 / INS-F-014).

## Carte physique

```text
~/acme-ai-team/                 ← Instance (Git) — ouvrir Cursor ici
  .ai-team/                    ← autorité (catalogue, ensembles, runtime)
  .cursor/                     ← adaptateur compilé
  <ensemble>.code-workspace    ← généré après set-active / register-member

~/code/boutique-api/           ← Membre backend (autre Git)
  .ai-team/member-link.json    ← lien mince seulement
  AGENTS.md                    ← pointeur vers l’instance

~/code/boutique-web/           ← Membre frontend
~/code/boutique-admin/         ← Membre backoffice
```

## Installer une instance vide

Depuis le dépôt framework :

```bash
mkdir ~/acme-ai-team && cd ~/acme-ai-team && git init -b main
python /chemin/vers/framework/tools/assess.py --target . --json --report-file assessment.json
python /chemin/vers/framework/tools/install.py \
  --target . \
  --project-id acme-ai-team \
  --project-name "Acme AI Team" \
  --assessment-report assessment.json
```

Effet : `.ai-team/catalog.yaml` vide (`ensembles: []`). Aucun dépôt produit n’est encore déclaré.

## Enregistrer un Ensemble et des Membres

Depuis l’**instance** (pas depuis un membre) :

```bash
python scripts/ai-team/ensemble.py register-ensemble --id boutique --name "Boutique"
python scripts/ai-team/ensemble.py register-member \
  --ensemble boutique --id backend --kind service --path ../code/boutique-api
python scripts/ai-team/ensemble.py register-member \
  --ensemble boutique --id frontend --kind ui --path ../code/boutique-web
python scripts/ai-team/ensemble.py register-member \
  --ensemble boutique --id backoffice --kind ui --path ../code/boutique-admin
python scripts/ai-team/ensemble.py set-active --id boutique
```

Chaque `register-member` pose le lien mince sur le checkout membre. `set-active` et `register-member` régénèrent `<ensemble>.code-workspace` à la racine de l’instance (CLI uniquement, pas le Gateway).

## Ouvrir Cursor

1. Ouvrir le répertoire **instance** (ou le fichier `.code-workspace` de l’Ensemble actif).
2. Ne pas lancer `/compile-project` depuis un membre seul : le lien mince refuse le cycle.
3. Les Work Units produit portent `member_id` ; le cwd d’exécution est le checkout (ou worktree) du membre.

## Migrer un install standalone 0.7.x → instance

Commande **explicite** (snapshot + rollback) :

```bash
python tools/migrate_to_instance.py \
  --source ~/code/boutique-api \
  --instance ~/acme-ai-team \
  --ensemble-id boutique \
  --member-id backend \
  --dry-run

python tools/migrate_to_instance.py \
  --source ~/code/boutique-api \
  --instance ~/acme-ai-team \
  --ensemble-id boutique \
  --member-id backend
```

- Déplace `.ai-team/`, `scripts/`, `.cursor/` vers l’instance.
- Laisse sur le produit un `member-link.json` + bloc `AGENTS.md`.
- En cas d’échec, restaure le source depuis le snapshot local
  (`.in-tree-to-instance-*` à côté du produit) ; en succès, archive zip sous
  `instance/.ai-team/migration-backups/`.

Ensuite, enregistrer d’éventuels autres membres (`frontend`, `backoffice`) comme ci-dessus.

## Ce que `--update` ne fait pas

```bash
python tools/install.py --target ~/code/mon-app --update
```

Sur un standalone 0.7.x, la mise à jour rafraîchit les fichiers gérés **in-tree**. Elle ne crée pas d’instance, ne pose pas de lien mince, et ne déplace pas `.ai-team/`.
