# Frontière d’intégration — Feedback Export

Le framework produit localement un snapshot Feedback JSON. Un consommateur
externe peut le transporter et le traiter, sans devenir une dépendance du
Command Gateway ou du fonctionnement hors ligne du framework.

## Autorité

| Élément | Propriétaire |
|---|---|
| Génération, niveaux `aggregate`/`structured`/`full`, consentement local | framework |
| Schéma `format_version: "1.1"` | framework |
| Transport, HMAC, endpoint HTTP, accusé distant | projet consommateur externe |
| Stockage, rétention distante, agrégats et exploitation | projet consommateur externe |

Le schéma distribué et validé par le framework est
[`distribution/payload/.ai-team/schemas/feedback-export.schema.json`](../../../distribution/payload/.ai-team/schemas/feedback-export.schema.json).
Le comportement producteur est décrit dans le
[modèle tactique Feedback](../../framework-design/architecture-and-constraints/10-modele-tactique-feedback.md).

Le consommateur doit verrouiller une version exacte du schéma, enregistrer sa
provenance et tester ses fixtures contre celle-ci. Il ne doit pas redéfinir
manuellement la structure du corps dans un second contrat divergent.

Voir [compatibility.md](compatibility.md) pour les règles d’évolution.
