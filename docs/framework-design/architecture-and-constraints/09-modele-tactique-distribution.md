# Document 9 — Modèle tactique : Distribution/Installation

**Statut** : version 1.1 corrigée.

## 1. État actuel

- `tools/install.py:COPY_ITEMS` livre `.cursor` et `.ai-team` dans un même ensemble.
- `.ai-team/framework-version.json` porte une version globale.
- `SUPPORTED_UPDATE_FROM` exprime une compatibilité globale.
- `managed_files` est généré et utilisé pour détecter les fichiers autrefois gérés devenus obsolètes.
- La mise à jour réalise snapshot, copie, validation et rollback en cas d’exception.

La cible doit séparer noyau et Adaptateurs sans perdre `managed_files` ni le rollback.

## 2. Installation Record cible

```json
{
  "schema_version": 2,
  "project_id": "example-project",
  "core": {
    "version": "0.4.0",
    "managed_files": [".ai-team/schemas/work-unit.schema.json"]
  },
  "adapters": [
    {
      "id": "cursor",
      "version": "0.4.0",
      "managed_files": [".cursor/agents/backend-developer.md"]
    }
  ],
  "distribution": {
    "version": "0.4.0",
    "managed_files": ["tools/install.py"]
  },
  "installed_at": "2026-08-28T10:00:00Z",
  "last_updated_at": "2026-08-28T10:00:00Z"
}
```

Le manifeste réel doit conserver la liste complète des fichiers. L’exemple n’est pas une liste normative.

### Invariants

1. Un seul record par `project_id`.
2. Identifiants d’Adaptateur uniques.
3. `active_adapter_id` du Project Profile correspond à exactement une entrée installée.
4. La version active vient de ce record, jamais d’une copie dans le Project Profile.
5. Chaque composant possède ses `managed_files` afin que mise à jour et désinstallation ne suppriment que ce qu’il gère.
6. La compatibilité `core`/Adaptateur est validée avant copie.
7. Les timestamps sont UTC et `last_updated_at >= installed_at`.

## 3. Agrégat et objets associés

`InstallationRecord` est un Agrégat cible plausible identifié par le projet. Il protège la composition installée et la possession des fichiers. Une entrée `AdapterInstallation` peut être une Entité interne si son cycle de vie doit être adressé séparément ; `AdapterRelease` reste une valeur versionnée.

## 4. Protocole de mise à jour cible

1. Lire et valider le manifeste existant, y compris `managed_files`.
2. Vérifier compatibilité et migration de schéma v1 → v2.
3. Prendre un snapshot récupérable des fichiers affectés.
4. Appliquer noyau, Adaptateurs et distribution dans une zone temporaire ou transaction simulée.
5. Exécuter migrations publiées, validations et tests de conformité.
6. Remplacer atomiquement autant que le système de fichiers le permet.
7. Écrire le nouvel Installation Record en dernier.
8. En cas d’échec, restaurer le snapshot et conserver un diagnostic.

Les migrations peuvent modifier des données projet, mais uniquement comme opérations explicites, versionnées, validées et réversibles. La règle précédente « Distribution ne modifie jamais l’état » est remplacée par cette contrainte vérifiable.

## 4bis. Assessment d’adoption (cible, Document 19)

Avant une **install fraîche**, Distribution DOIT offrir (cible) un parcours d’**assessment** non mutant qui inventorie les conflits de gouvernance et d’artefacts sur la cible et produit un verdict `go` / `go_with_backlog` / `no_go`. Cet assessment :

- n’écrit pas l’arbre cible ;
- n’est pas une Gate G0–G4 ;
- ne constitue pas un mode de gouvernance partielle ;
- précède la Décision d’adoption humaine puis l’écriture de l’Installation Record ;
- expose la catégorie `baseline` (matière humaine / inventaire as-built) comme engagement **post-install pré-compile**, sans traiter le dépôt comme autorité produit.

Les collisions de chemins à l’install restent un garde-fou technique ; elles ne remplacent pas l’inventaire d’autorité / process / artefacts concurrents ni la baseline produit.

## 5. Domain Events de Distribution

Les faits candidats sont `InstallationCompleted`, `UpdateApplied` et `UpdateRolledBack`. Ils ne peuvent pas être injectés tels quels dans `event.schema.json`, dont l’énumération Gouvernance est fermée et dont le modèle mélange plusieurs natures de messages.

S’ils sont nécessaires, Distribution doit publier son propre schéma d’événements immuables et préciser leur émission après commit de l’opération. Une intégration vers Gouvernance se fait par traduction explicite, pas par réutilisation nominale de StructuredEvent.

## 6. Possession des fichiers observée

`PROJECT_OWNED_PATTERNS` protège les principaux objets Gouvernance, `project-profile.yaml.bak`, ainsi que les espaces Feedback. Quatre familles supplémentaires ne correspondent pas directement à un Agrégat Gouvernance : `audits/`, `logs/`, `metrics/`, `migration-backups/`. `observations/` et `retrospectives/` appartiennent à Feedback ; `metrics/` conserve notamment les exports par défaut.

La liste de possession reste définie actuellement dans Distribution. La cible doit la publier par composant dans le manifeste et la valider contre une politique commune.

## 7. Limites

- `adapters[]` n’est éprouvé qu’avec Cursor.
- La matrice de compatibilité, la désinstallation et le multi-adaptateur restent à spécifier.
- La migration v1 → v2 doit préserver les anciens `managed_files`.
- Le modèle des événements de Distribution n’est pas implémenté.
- L’assessment d’adoption (Document 19) est livré via `tools/assess.py` ; le garde-fou install `--assessment-report` est actif. La détection `authority` reste partielle ; la catégorie `baseline` est heuristique (racines de code / `docs/product/`).

## Sources

`tools/install.py` (`COPY_ITEMS`, `PROJECT_OWNED_PATTERNS`, `SUPPORTED_UPDATE_FROM`, génération et lecture de `managed_files`), `.ai-team/framework-version.json`.
