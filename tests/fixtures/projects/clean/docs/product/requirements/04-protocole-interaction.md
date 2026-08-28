# Document 4 — Protocole d’interaction noyau ↔ Adaptateur

**Statut** : version 1.1 corrigée. Ce document distingue le comportement actuel de la cible.

## 1. Principe

Le Runtime peut retourner du texte ou un résultat natif au Control Plane. Ce retour opérationnel peut être lu pour orchestrer, mais **ne constitue ni une preuve suffisante, ni une autorisation de transition, ni une écriture d’état faisant autorité**.

La règle correcte n’est donc pas « le noyau ne lit jamais la sortie brute ». Elle est :

> Une transition de Gouvernance doit être décidée à partir d’artefacts validés et de commandes autorisées ; une déclaration d’agent ne suffit jamais à elle seule.

## 2. Séquence cible

1. **Résolution** : lire l’`active_adapter_id`, l’Installation Record et la version du Published Contract Bundle.
2. **Sélection** : choisir `role_id`, révision et `procedure_id`, révision compatibles.
3. **Compilation/chargement** : l’Adaptateur résout les artefacts natifs et vérifie les capacités.
4. **Exécution** : l’outil exécute sous les capacités et approbations calculées.
5. **Retour opérationnel** : l’Adaptateur retourne un `RuntimeResult` avec identités, état technique, références de sortie et texte éventuel.
6. **Soumission** : les preuves, constats, signaux et demandes sont soumis aux commandes du noyau puis validés par schéma et invariants.
7. **Décision** : le Control Plane relit l’état faisant autorité et choisit la suite. Une transition refusée reste refusée même si le RuntimeResult annonce un succès.

## 3. Réalité Cursor actuelle

- Les agents développeurs renvoient un handoff structuré dans leur réponse.
- Le Reviewer doit retourner une disposition textuelle déterminée.
- Aucun mécanisme ne force ces réponses à être persistées et validées avant lecture par la session principale.
- Les artefacts Cursor sont pré-écrits ; aucune compilation dynamique Rôle/Procédure n’existe encore.

Le protocole cible constitue donc un changement à implémenter, pas un invariant déjà présent.

## 4. Trace : compilation

### Observé aujourd’hui

1. L’humain invoque explicitement `compile-project`.
2. La session principale lit Constitution, Project Profile et Source Registry.
3. Elle prépare Work Units, dépendances, risques et contexte.
4. Elle propose une allowlist.
5. Elle écrit directement Project State et Work Units puis attend G1.

### Cible

Les étapes métier restent identiques, mais les créations et transitions passent par des commandes du noyau (`CreateWorkUnit`, `SetCompilationState`, etc.). L’Adaptateur traduit l’invocation et les capacités ; il ne décide pas G1.

## 5. Trace : Work Unit vers preuve

1. Le Control Plane sélectionne une Work Unit prête.
2. Il construit un Context Package.
3. Il délègue avec l’identité exacte du bundle, du Rôle et de la Procédure.
4. Le Développeur retourne un SHA et un RuntimeResult ; le noyau n’enregistre une preuve qu’après validation.
5. QA, Reviewer, Sécurité et Auditeur travaillent sur le SHA exact requis par la politique.
6. Le noyau rattache les artefacts validés aux outcomes.
7. Si le SHA change, une commande invalide les preuves liées à l’ancien SHA et empêche `done` jusqu’à nouvelle vérification.

L’étape 7 est une cible : `check_done.py` vérifie actuellement la présence de preuves, pas leur SHA.

## 6. Types de retour

- **Evidence** : résultat observé validé.
- **Finding** : constat d’audit validé.
- **Decision Request** : question humaine persistée.
- **Gate Decision** : décision humaine de gate persistée par la commande dédiée.
- **Workflow Message** : message de coordination avec statut, distinct d’un Domain Event.
- **Domain Event** : fait métier passé, immuable, produit après réussite transactionnelle d’une commande.

Le terme ambigu `Decision` n’est pas utilisé seul.

## 7. Limites

- Aucun autre Adaptateur n’a exécuté ce protocole.
- Aucun test end-to-end ne démontre encore les sept étapes, même sur Cursor.
- Les scénarios remédiation, concurrence, timeout, reprise et décision en attente devront être spécifiés.
- L’atomicité des commandes et le format exact du RuntimeResult restent à concevoir.

## Sources

`.cursor/skills/compile-project/SKILL.md`, `orchestrator/SKILL.md`, `build-context/SKILL.md`, `.cursor/agents/backend-developer.md`, `code-reviewer.md`, `scripts/ai-team/check_done.py`.
