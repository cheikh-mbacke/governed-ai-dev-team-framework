# Notifications e-mail

Les notifications e-mail signalent une action humaine utile. Elles ne remplacent
ni les événements structurés, ni `status.py`, ni une gate, et un échec SMTP ne
bloque jamais une Work Unit ou un Run.

## Configuration livrée

Les installations neuves reçoivent ces valeurs publiques :

- serveur `mail.agenteam.fr` ;
- port `465` ;
- sécurité `ssl` avec validation du certificat ;
- nom d'utilisateur et expéditeur `support@agenteam.fr` — l'adresse complète est
  obligatoire ;
- secret lu dans `GOVERNED_AI_SMTP_PASSWORD` ou, à défaut, dans le fichier local
  gitignoré `.ai-team/secrets/smtp.json`.

Le mot de passe ne doit jamais être ajouté au profil, à Git, à un événement ou à
une commande enregistrée. Exemple de fichier local :

```json
{
  "password": "<secret SMTP>"
}
```

Au moins un destinataire doit ensuite être renseigné dans
`.ai-team/project-profile.yaml` :

```yaml
notifications:
  email:
    recipients:
      critical:
        - responsable-technique@example.com
      action_required:
        - product-owner@example.com
      digest:
        - equipe@example.com
```

La priorité `critical` retombe sur `action_required`, puis sur `digest`, si son
groupe est vide. `action_required` retombe sur `digest`. Le framework n'envoie
jamais les informations d'un projet à `support@agenteam.fr` par défaut : cette
adresse est le compte expéditeur, pas un destinataire implicite.

Pour utiliser le port `587`, remplacer `port: 465` et `security: ssl` par :

```yaml
port: 587
security: starttls
```

## Événements

| Événement | Livraison par défaut |
|---|---|
| arrêt global ou Run en échec | immédiate, groupe `critical` |
| décision humaine requise | immédiate, groupe `action_required` |
| escalade de risque | immédiate, groupe `action_required` |
| release candidate prête pour G3 | immédiate, groupe `action_required` |
| incrément prêt pour vérification humaine | immédiate en mode supervisé, digest en mode autonome |
| checkpoint UI | immédiate en mode supervisé, digest en mode autonome |
| retour UI réconcilié | digest |
| Run terminé | digest |

Une valeur peut être remplacée par `immediate`, `digest`, `off` ou `profile`
dans `notifications.email.events`. `profile` signifie temps réel en mode
supervisé et digest dans les profils `unattended_*`.

## Exploitation

```bash
python scripts/ai-team/notify.py status
python scripts/ai-team/notify.py configure-secret
python scripts/ai-team/notify.py test --to vous@example.com
python scripts/ai-team/notify.py dispatch
python scripts/ai-team/notify.py digest
```

L'orchestrateur appelle automatiquement `dispatch` après chaque tick et envoie
le digest groupé à la fin du Run. Les envois sont dédupliqués par événement et
révision. En cas d'échec, le record reste sous `.ai-team/notifications/` avec un
délai exponentiel avant nouvelle tentative. Le transport essaie au maximum six
fois et ne propage jamais son échec au cycle d'exécution.

`status.py` indique si SMTP est prêt et combien de notifications attendent.
