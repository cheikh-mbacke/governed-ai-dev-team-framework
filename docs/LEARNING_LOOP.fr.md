# Boucle d'apprentissage du framework

La boucle d'apprentissage distingue trois niveaux qui ne doivent pas être
confondus :

1. un **événement opérationnel** (`BLOCKER`, `DEFECT`, `DECISION_REQUEST`, ...)
   pilote le travail actuel ;
2. une **observation** décrit une friction potentiellement réutilisable pour
   améliorer le framework ;
3. une **rétrospective** agrège les objets déjà enregistrés sans inventer de
   causalité.

## Enregistrer une friction

```bash
python scripts/ai-team/feedback.py record \
  --category context \
  --severity medium \
  --origin unknown \
  --confidence low \
  --work-unit WU-014 \
  --symptom "Le contrat partagé manquait dans le Context Package" \
  --blocked-minutes 35 \
  --rework-required \
  --human-intervention \
  --evidence-ref EVT-042 \
  --recurrence-key missing-shared-contract-context
```

Utilise `origin: unknown` tant que les preuves ne permettent pas de distinguer
un défaut du framework, du projet, de l'environnement, d'un service externe ou
du processus humain. Une observation ne remplace jamais le `BLOCKER` ou le
`DEFECT` requis pour le runtime.

Les catégories disponibles sont : `readiness`, `decomposition`, `context`,
`staffing`, `permissions`, `orchestration`, `tooling`, `testing`, `review`,
`audit`, `human_gate`, `environment`, `documentation` et `other`.

## Produire une rétrospective

```bash
python scripts/ai-team/feedback.py retrospective --work-unit WU-014
python scripts/ai-team/feedback.py retrospective --project
```

Les fichiers sont créés sous `.ai-team/retrospectives/`. Ils contiennent des
comptages traçables : observations, événements, décisions, findings, recettes,
minutes bloquées, reprises et interventions humaines.

## Exporter pour une analyse inter-projets

```bash
# Recommandé : champs structurés, sans identifiant projet ni texte libre
python scripts/ai-team/feedback.py export

# Comptages uniquement
python scripts/ai-team/feedback.py export --detail-level aggregate

# Contenu complet : à relire avant tout partage
python scripts/ai-team/feedback.py export --detail-level full
```

Les exports sont écrits sous `.ai-team/metrics/`. Le niveau `structured` est le
défaut : il remplace l'identité du projet par un hash stable, exclut les symptômes
et améliorations en texte libre, et transforme la clé de récurrence en référence
hachée. Le niveau `full` peut contenir des informations sensibles au projet.

## Validation et analyse

`python scripts/ai-team/validate.py` valide chaque observation et rétrospective,
ainsi que les références d'observation conservées par les rétrospectives.
`python scripts/ai-team/status.py` affiche le nombre d'observations non résolues
et leur répartition par catégorie.

Une corrélation n'est pas une cause : plusieurs occurrences doivent être
comparées avec leurs preuves avant de modifier la Constitution ou les defaults
du framework.
