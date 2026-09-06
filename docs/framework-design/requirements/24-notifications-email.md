# Exigence 24 — notifications e-mail non bloquantes

## Décision

Le Control Plane doit pouvoir transmettre par SMTP les événements nécessitant
une attention humaine, tout en conservant les événements et objets gouvernés
comme source de vérité. Le courrier est un canal de projection faillible : son
indisponibilité ne modifie jamais un état, une gate, un plafond ou un résultat.

## Classes

- `critical` : arrêt global ou échec de Run ; livraison immédiate ;
- `action_required` : décision, escalade, G3 ou vérification humaine disponible ;
- `digest` : checkpoint UI non supervisé, réconciliation et rapport de Run.

Les événements routés selon le profil sont immédiats sous supervision continue
et regroupés pour les profils non supervisés. Aucune transition ordinaire,
réussite de test, tentative récupérable ou commit ne produit un courrier.

## Contraintes

1. Le secret SMTP est lu depuis l'environnement ou un fichier gitignoré et
   n'apparaît jamais dans un artefact distribué, un log ou un message d'erreur.
2. SSL implicite sur 465 et STARTTLS sur 587 utilisent la validation de
   certificat du système.
3. L'expéditeur et chaque groupe de destinataires sont explicites ; aucun
   destinataire externe n'est implicite.
4. Une clé stable `(type, source, version)` empêche les doublons.
5. Les échecs sont persistés, retentés avec délai exponentiel et plafonnés.
6. Un digest est regroupé par ensemble de destinataires afin d'éviter toute
   fuite entre groupes.
7. Une notification ne constitue jamais une autorisation ou une acceptation.

## Configuration de référence

Le profil installe `mail.agenteam.fr:465`, `ssl`, et l'adresse complète
`support@agenteam.fr` comme compte et expéditeur. Le mot de passe et les
destinataires restent obligatoirement propres à l'environnement d'exploitation.
