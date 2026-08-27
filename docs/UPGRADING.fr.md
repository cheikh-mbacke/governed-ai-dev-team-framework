# Mettre à jour un projet déjà installé

Utilise l'installeur du **nouveau clone du framework**, pas une éventuelle
copie ancienne présente dans le projet cible. L'upgrade est transactionnel et
préserve l'état propre au projet, mais remplace volontairement les fichiers de
gouvernance appartenant au framework.

## 1. Partir d'un working tree cible propre

Commite ou mets de côté tout travail en cours avant l'upgrade. Créer une
nouvelle branche n'isole pas les fichiers non commités : ils suivent le
checkout.

```bash
git status --short
# Seulement si la commande précédente montre un travail en cours :
git stash push -u -m "wip avant mise a jour framework"
git switch main
git switch -c chore/framework-update
```

Conserve le stash jusqu'à la revue et au merge de la branche framework, puis
au rebase de la branche de travail initiale. Préfère `git stash apply` lors de
la restauration : un échec ou un conflit ne supprimera pas la copie de secours.

L'installeur s'arrête avant toute écriture si la cible est sale ou n'est pas
un worktree Git autonome. `--allow-dirty` est un contournement d'urgence
explicite, pas le parcours normal.

## 2. Prévisualiser le plan complet

Depuis le clone à jour du framework :

```bash
python tools/install.py --target /chemin/vers/projet --update --dry-run
```

Le plan affiche :

- les versions installée et cible du framework ;
- les fichiers framework ajoutés ou remplacés ;
- les migrations de données projet ;
- les chemins sales éventuels ;
- les anciens fichiers gérés devenus obsolètes.

Si l'upgrade change la version de la Constitution, l'installeur ne l'active
que lorsque le Project State est `not_compiled` ou `completed`. Toute autre
phase correspond à un cycle encore ouvert : l'upgrade s'arrête avant d'écrire
afin de ne pas changer les règles sous une exécution en cours. Termine ou ferme
explicitement ce cycle, puis relance le dry-run.

Si tu as besoin du reste de la mise à jour (nouveaux scripts, docs,
migrations) sans attendre la clôture du cycle, passe
`--force-constitution-update`. Cela contourne le gel pour cette exécution et
active quand même la nouvelle Constitution. Les Work Units déjà gatées (G1-G4)
sous l'ancienne version ne sont **pas** revalidées rétroactivement —
l'installeur enregistre un événement `CONTRACT_CHANGE` sous
`.ai-team/events/` avec `requires_human: true`, à revoir avant leur prochain
gate. À traiter comme un contournement d'urgence explicite, pas comme le
fonctionnement normal.

Le dry-run n'utilise que la bibliothèque standard Python et ne modifie jamais
la cible. Les fichiers obsolètes sont signalés, mais jamais supprimés
automatiquement.

## 3. Appliquer l'upgrade

```bash
python tools/install.py --target /chemin/vers/projet --update
```

L'installeur cherche automatiquement un Python de validation dans le `.venv`
de la cible (POSIX ou Windows), puis essaie l'interpréteur qui exécute
l'installeur. PyYAML et jsonschema sont nécessaires pour la validation finale.

L'upgrade :

1. sauvegarde temporairement chaque fichier susceptible d'être touché ;
2. remplace uniquement les fichiers framework réellement différents ;
3. applique les migrations de données connues et idempotentes ;
4. écrit `.ai-team/framework-version.json` avec la version installée et le
   manifeste des fichiers gérés ;
5. lance `scripts/ai-team/validate.py` dans la cible ;
6. restaure automatiquement tous les fichiers touchés si la copie, la
   migration ou la validation échoue.

Les fichiers sources des migrations restent aussi sauvegardés sous
`.ai-team/migration-backups/`, dossier ignoré par Git.

`--skip-validation` existe uniquement comme contournement d'urgence explicite.
Une mise à jour réalisée avec cette option n'est pas considérée comme validée.

## 4. Revoir et tester

```bash
git status --short
git diff --check
git diff
python scripts/ai-team/preflight.py
```

Exécute les tests propres au projet, puis le smoke interactif Allowlist du
`docs/TERMINAL_GUIDE.fr.md`. Sous WSL/Linux, vérifie aussi séparément le
parcours `architect + workspace_readonly`.

## 5. Restaurer plus tard une Work Unit mise en stash

Un stash peut contenir d'anciennes données absentes pendant l'upgrade. Rebase
la branche Work Unit encore propre **avant** de restaurer le stash, puis lance
la migration idempotente autonome :

```bash
git switch wu/exemple
git rebase main
git stash apply stash@{0}
python scripts/ai-team/migrate.py
python scripts/ai-team/migrate.py --apply
python scripts/ai-team/validate.py
```

La première commande de migration est un dry-run. Ne supprime le stash
qu'après revue du travail restauré et validation réussie.

## Frontière de propriété

Les chemins framework mis à jour comprennent `.cursor/`,
`.ai-team/constitution/`, `.ai-team/schemas/`, `.ai-team/templates/`,
`scripts/`, `requirements.txt` et les README de catégorie sous
`docs/product/`.

Les profils, registres de sources, Work Units, états, décisions, événements,
preuves, findings, audits, releases, acceptances, context packages, logs,
sauvegardes de migration et documents produit rédigés restent préservés. Une
migration connue peut volontairement transformer un fichier projet ; chaque
fichier concerné apparaît dans le dry-run et est sauvegardé avant modification.
