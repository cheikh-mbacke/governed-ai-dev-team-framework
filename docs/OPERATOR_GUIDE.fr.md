# Guide opérateur

*[Read in English](OPERATOR_GUIDE.md)*

Ce guide détaille chaque étape. Pour le chemin rapide, voir le Quickstart de
`README.fr.md` — les deux se correspondent, ce guide donne juste plus de
contexte sur chaque étape.

## 1. Installer le framework

Utiliser `tools/install.py`. Le framework est copié dans le repo projet sans supposer la stack technique. Le dossier `examples/` du framework n'est jamais copié.

## 2. Remplir la matière de construction

Placer les documents humains dans `docs/product/` puis compléter `.ai-team/sources/source-registry.yaml`. Un exemple commenté est déjà présent en haut du fichier.

Une source doit indiquer :

- son identifiant stable ;
- son chemin ou URI ;
- son autorité ;
- sa portée ;
- sa version ;
- son statut.

## 3. Compléter le profil projet

Le fichier `.ai-team/project-profile.yaml` contient les commandes techniques du projet : build, lint, tests, chemins source/tests/docs, environnement et règles de release. Un exemple commenté est en haut du fichier. C'est le seul autre fichier réellement vide — tout le reste de la Constitution est déjà un default fonctionnel.

## 3b. Perimetre linguistique

`communication.language` dans `project-profile.yaml` regle la facon dont les
agents vous parlent et la prose destinee a l'humain qu'ils redigent a
l'execution — titres de Work Unit, questions, rapports generes. Ca ne change
jamais les cles YAML, les valeurs d'enum, les chemins de fichiers, les
commandes ou le code, et ca ne change jamais non plus les fichiers livres
par le framework lui-meme :

- La Constitution, `AGENTS.md`, et les regles/agents/skills Cursor sous
  `.cursor/` restent en anglais, dans tous les projets, quel que soit
  `communication.language`. Ces fichiers sont lus par l'agent pour gouverner
  son propre comportement, pas par vous directement, et une copie traduite
  d'un texte normatif risquerait de diverger silencieusement de l'original
  anglais — deux "sources de verite" pour la meme regle, c'est pire qu'une
  seule source dans une langue qu'on lit une fois.
- `docs/product/*/README.md` (les dossiers de matiere de construction) et ce
  guide ont une traduction francaise (`*.fr.md`) maintenue a la main, de la
  meme facon que `README.fr.md` existe a cote de `README.md` a la racine du
  depot.
- Les quelques scripts sous `scripts/ai-team/` qui affichent directement
  dans votre terminal (`status.py`, `check_done.py`, `feedback.py`,
  `diagnose.py`) lisent `communication.language` et affichent leurs
  libelles fixes en francais quand c'est le cas — voir
  `scripts/ai-team/i18n.py`. `validate.py` et `preflight.py` traduisent
  leur ligne d'en-tete mais laissent le corps des erreurs et diagnostics en
  anglais partout, car il est construit a partir de chemins de fichiers, de
  cles YAML, et de messages des bibliotheques PyYAML/jsonschema qui ne sont
  jamais traduits non plus.

## 4. Ouvrir le projet dans Cursor

Utiliser au choix l'IU Cursor ou le Cursor CLI interactif sur le **projet
installé** (pas ce dépôt framework). Dans l'IU, faire confiance au workspace.
Dans le terminal, lancer `agent --workspace "$PWD"` depuis la racine du projet.
Les deux modes découvrent `.cursor/rules/`, `.cursor/agents/`,
`.cursor/skills/` et `.cursor/hooks.json`, et partagent `.ai-team/`. Ne pas les
laisser écrire en même temps dans le même checkout. Voir
`TERMINAL_GUIDE.fr.md` pour la configuration et le smoke test CLI Allowlist
(via `auth-smoke`, pas le chat Agent de l'IU).

## 5. Compiler avant de développer

Dans l'IU ou le CLI Cursor, invoquer explicitement le Skill (il n'est pas
auto-déclenché) :

```text
/compile-project

Compile le projet à partir de @docs/product/. N'implémente aucun code
produit — arrête-toi après avoir produit le plan d'exécution pour mon
approbation.
```

Le Compiler doit produire ou mettre à jour :

- `.ai-team/state/project-state.yaml` ;
- `.ai-team/work-units/*.yaml` ;
- dépendances ;
- niveaux de risque ;
- vérifications requises ;
- plan de contexte ;
- staffing initial ;
- décisions manquantes.

Aucun code produit n'est modifié pendant cette étape.

## 6. Approuver G1

L'humain inspecte le plan. Il approuve, demande correction ou refuse. Une approbation est enregistrée dans `.ai-team/decisions/` et dans le Project State.

## 7. Activer l'orchestrateur

Utiliser le Skill `orchestrator` comme Custom Mode ou l'invoquer explicitement. Le Control Plane sélectionne uniquement les Work Units prêtes, dans les limites WIP.

## 8. Exécution

Pour chaque Work Unit :

1. construire un Context Package minimal ;
2. choisir le staffing ;
3. déléguer au Developer approprié ;
4. exécuter les vérifications développeur et inspecter le diff ;
5. créer un commit cohérent sur la branche de la Work Unit, avec son ID dans le message ;
6. transmettre son SHA exact à QA et au Reviewer ;
7. déclencher QA ;
8. déclencher Reviewer ;
9. déclencher Security si la politique l'impose ;
10. déclencher Auditor si la politique l'impose ;
11. produire la recette humaine ;
12. fermer seulement quand la Definition of Done est satisfaite.

Le Developer n'a pas besoin de demander une confirmation humaine pour chaque
commit cohérent sur sa branche isolée. Il doit en revanche s'arrêter avant tout
commit sur la branche protégée, merge, push non autorisé ou réécriture d'historique.
Après une remédiation, un nouveau commit est créé et les vérifications affectées
sont rejouées sur le nouveau SHA. Un commit WIP peut sauvegarder un travail
interrompu mais ne peut pas entrer en QA comme candidat vérifié.

## 9. Si ça semble bloqué

**D'abord, avant tout script** : dans l'IU, remonte dans le chat et cherche un
bouton "Run"/"Approve" ; dans le CLI, cherche une demande d'autorisation en
attente dans le terminal parent. C'est la cause la plus
fréquente et la plus invisible — une commande qui n'était pas
auto-approuvée (démarrer le serveur local, lancer Playwright, installer
une dépendance) suspend l'agent *avant* qu'il ait la main pour écrire
quoi que ce soit. Rien de ce que ce framework enregistre ne peut détecter
cet état, parce qu'aucun événement n'est écrit tant que la commande n'a
pas été exécutée. Si tu retombes souvent sur ce cas précis pour un type
de commande donné, ajoute une règle correspondante dans
`.cursor/permissions.json` → `autoRun.allow_instructions` pour l'IU, ou un
token de permission exact dans `.cursor/cli.json` pour le CLI, plutôt que de
l'approuver à chaque fois.

Si ce n'est pas ça, avant d'arrêter et de relancer — la seule option
quand tu n'as rien de concret à regarder — lance :

```bash
python scripts/ai-team/diagnose.py
```

Ce script répond, sans rien modifier, à trois questions dans l'ordre :

1. **Y a-t-il un événement `BLOCKER`/`CLARIFICATION_REQUEST`/`DECISION_REQUEST`
   ouvert et marqué `requires_human: true`** dans `.ai-team/events/` ? Si
   oui, c'est ça la vraie cause — résous-le, pas besoin de redémarrer quoi
   que ce soit.
2. **Quelles Work Units sont "en vol"** (ni `ready` ni `done`) ?
3. **Quand a eu lieu la dernière activité Cursor enregistrée**
   (`.ai-team/logs/cursor-events.jsonl`) ? Si ça fait longtemps et qu'aucun
   événement n'explique pourquoi, c'est un vrai blocage silencieux — pas
   un problème de ta part.

La Constitution exige maintenant qu'un agent qui ne peut pas continuer
écrive un `BLOCKER` avant de s'arrêter (`80-communication-policy.yaml` §
`never_stop_silently`) — si tu tombes quand même sur un arrêt sans aucune
trace, c'est un vrai manquement à signaler, pas juste "relance et
espère". Dans ce cas précis seulement, demande d'abord à l'agent
concerné ce qu'il était en train de faire avant de couper la session —
ça donne une chance d'obtenir la raison plutôt que de la perdre.

## 10. Décision manquante

Une décision produit absente devient `DECISION_REQUEST`, jamais une supposition. Seules les Work Units dépendantes sont bloquées.

## 11. Release

Une release candidate lie un commit/ensemble de commits, migrations, preuves, reviews, findings ouverts et rollback plan. G3 protège la production.

## 12. Recette

Les agents préparent les scénarios. L'humain exécute et enregistre PASS / FAIL / PARTIAL. Un échec produit un Defect et une Work Unit de remédiation.
