# Retours UI asynchrones

Le framework distingue trois actes humains :

1. le **checkpoint visuel**, notification non bloquante qu'une surface est
   testable sur un commit précis ;
2. le **retour humain formatif**, commentaire réconcilié avec l'état courant du
   projet ;
3. l'**acceptation G4**, décision formelle sur un incrément ou une release.

Un checkpoint ouvert n'est jamais une gate. En mode non supervisé, les agents
continuent jusqu'au plafond du profil : branche Work Unit vérifiée, branche
d'intégration vérifiée ou release candidate vérifié. L'absence de retour ne
change ni le statut de la Work Unit, ni le plafond, ni les gates.

## Quand tester

`/compile-project` sélectionne les checkpoints utiles pendant la préparation de
G1. Ils sont réservés à une première tranche testable, un nouveau parcours, une
modification d'architecture de l'information, un parcours critique, une forte
ambiguïté produit ou une modification matérielle d'une surface déjà examinée.

La QA publie le checkpoint après avoir elle-même observé les états applicables
sur un SHA stable. Le cahier associé contient trois à sept scénarios manuels,
l'URL ou la commande, les préconditions, les données, les résultats attendus,
les limites connues et les preuves. Il vise le jugement humain utile — clarté,
priorités, vocabulaire métier, confiance — et ne répète pas tous les contrôles
automatisés.

Les checkpoints ouverts sont visibles avec :

```bash
python scripts/ai-team/status.py
```

## Enregistrer un retour

Depuis le projet installé :

```bash
python scripts/ai-team/human_feedback.py \
  --work-unit WU-UI-001 \
  --surface dashboard \
  --sha 0123456789abcdef0123456789abcdef01234567 \
  --checkpoint EVT-UI-CHECKPOINT \
  --acceptance-package .ai-team/acceptance/UAT-UI-001.yaml \
  --scenario UI-01=passed \
  --scenario UI-02=failed \
  --comment "L'action principale n'est pas assez visible." \
  --by product-owner
```

La commande crée `.ai-team/human-feedback/HF-*.yaml`, ferme le checkpoint
informatif et laisse la Work Unit dans son statut courant. Elle ne vaut pas
acceptation G4.

## Réconciliation

Avant la prochaine exécution d'un nœud affecté, le Control Plane compare le SHA
observé au code courant et classe le retour :

- défaut encore présent ;
- ajustement UX ;
- changement d'intention produit ;
- déjà satisfait par un changement ultérieur ;
- devenu obsolète.

Il calcule les Work Units touchées, conserve les anciennes preuves comme faits
historiques, enregistre celles devenues obsolètes, puis crée les nouvelles Work
Units de remédiation ou une Decision Request. Seul un véritable choix produit
non couvert peut bloquer son sous-graphe ; les travaux indépendants continuent.

`status.py` affiche les retours en `pending_reconciliation` pour qu'aucun retour
ne reste seulement dans une conversation.
