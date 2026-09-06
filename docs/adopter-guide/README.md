# Guide d’adoption

Guides pratiques pour **décider d’adopter**, installer, migrer, valider et exploiter le framework **sans lire le code source**.

| Document | Usage |
|---|---|
| [adoption-assessment.md](adoption-assessment.md) | **Avant install** — gouvernance exclusive, grille des conflits, verdict GO/NO-GO |
| [project-reconciliation.md](project-reconciliation.md) | **Après install, avant compile** — matière humaine, inventaire as-built, convergence et baseline |
| [architecture.md](architecture.md) | Comprendre les composants et leurs responsabilités |
| [security-model.md](security-model.md) | Autorité humaine, gates et frontières de confiance |
| [operator-guide.md](operator-guide.md) | Commandes quotidiennes (install, update, validate, rollback) |
| [asynchronous-ui-feedback.md](asynchronous-ui-feedback.md) | Tester une UI au bon moment et réinjecter un retour sans bloquer les modes autonomes |
| [email-notifications.md](email-notifications.md) | Configurer SMTP, les destinataires, les alertes immédiates et les digests |
| [upgrading.md](upgrading.md) | Passage `0.4.x` → `0.7.0` et Installation Record v3 |
| [adopter-checklist.md](adopter-checklist.md) | Checklist de mise en service (assessment → G0…) |
| [deprecations.md](deprecations.md) | Scripts et formats dépréciés |

L’assessment d’adoption précède l’installation. Les autres guides décrivent surtout
le framework **une fois installé**. Les documents métier du produit client restent
dans son propre `docs/product/` et sont project-owned. La conception normative du
framework source reste sous [`docs/framework-design/`](../framework-design/)
(notamment Documents 19–20).
