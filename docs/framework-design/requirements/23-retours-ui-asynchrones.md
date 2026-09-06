# Document 23 — Checkpoints UI et retours humains asynchrones

## 1. Intention

Permettre à un humain d'essayer une interface assez tôt pour infléchir le
produit, sans transformer chaque revue visuelle en gate et sans interrompre un
Run non supervisé.

## 2. Invariants

- Un checkpoint UI formatif est émis après QA indépendante sur un SHA stable.
- Sa simple ouverture ou l'absence de réponse humaine ne modifie aucun statut,
  gate, plafond d'exécution ou cible de livraison.
- Le profil d'autonomie détermine jusqu'où l'exécution continue ; tous les
  profils non supervisés traitent le checkpoint comme non bloquant.
- Un retour humain mentionne le SHA réellement testé, la surface, la Work Unit
  et les scénarios exécutés lorsqu'ils sont connus.
- Le retour est comparé à l'état courant avant toute remédiation.
- Les preuves anciennes restent immuables ; la réconciliation désigne celles
  que le changement rend obsolètes.
- Le système continue les Work Units indépendantes. Seul un choix produit non
  couvert peut bloquer le sous-graphe qui en dépend.
- Le retour formatif ne satisfait jamais `human_acceptance` et ne décide pas G4.

## 3. Sélection et cadence

La sélection est explicite dans `WorkUnit.human_ui_review` lors de la
compilation/G1. Elle vise les premières tranches testables, nouveaux parcours,
changements d'architecture de l'information, parcours critiques, ambiguïtés
produit et modifications matérielles de surfaces déjà examinées. Les
refactorings invisibles et changements sans effet perceptible sont exclus par
défaut.

Un seul checkpoint ouvert par Work Unit et surface est autorisé. Un nouveau
checkpoint n'est émis qu'après une modification matérielle ou de contrat.

## 4. Cycle de réconciliation

1. QA publie le cahier de scénarios et le checkpoint.
2. L'exécution continue selon le profil.
3. `RecordHumanFeedback` persiste le retour en `pending_reconciliation` sans
   modifier l'exécution.
4. Le Control Plane compare le SHA observé au SHA courant et exécute l'analyse
   d'impact.
5. Les actions nécessaires sont créées par les commandes gouvernées existantes
   — Work Unit de remédiation, reverification, Context Package ou Decision
   Request.
6. `ReconcileHumanFeedback` enregistre classification, applicabilité, nœuds
   affectés, preuves obsolètes et références d'action.
7. Le graphe reprend au premier nœud réellement invalidé.

## 5. Stockage

`HumanFeedback` est stocké sous
`.ai-team/human-feedback/{feedback_id}.yaml`. Les statuts sont
`pending_reconciliation`, `reconciled`, `needs_decision` et `superseded`.
