# Document 8 — Classification tactique : Rôle, Procédure et Adaptateur

**Statut** : version 1.1 corrigée. La classification distingue l’identité métier de sa définition versionnée.

## 1. Principes

- Une **Entité** possède une identité et une continuité pertinentes pour le domaine.
- Un **Objet-Valeur** est défini par ses attributs et est remplacé plutôt que muté.
- Un **Agrégat** possède une racine Entité et une frontière transactionnelle qui impose des invariants.
- Un composant technique ou service n’a pas à être forcé dans l’une de ces catégories.

## 2. Rôle

- **RoleId / Rôle conceptuel** : identité stable telle que `backend-developer`; candidat Entité si le domaine doit suivre sa continuité.
- **RoleDefinitionRevision** : Objet-Valeur immuable, identifié techniquement par version ou hash de contenu.

Le besoin d’audit n’impose donc pas de classer tout le Rôle comme Objet-Valeur. Une Work Unit doit conserver `bundle_version`, `role_id` et `role_revision`/`content_hash`. Un snapshot complet reste optionnel si le bundle immuable est durablement accessible.

## 3. Procédure

- **ProcedureId** : identité stable de la pratique.
- **ProcedureRevision** : Objet-Valeur immuable et versionné.

La même distinction permet d’auditer une exécution sans laisser `event.details` porter une structure libre et non validée.

## 4. PublishedContractBundle comme Agrégat cible

Un bundle unique contient les révisions de Rôles et Procédures publiées ensemble.

- **Racine** : `PublishedContractBundle` identifié par sa version.
- **Invariants** : unicité des identifiants/révisions ; toute `procedure_ref` d’un Rôle résout une Procédure du bundle ; compatibilité des capacités et sorties ; contenu figé après publication.
- **Transaction** : validation et publication atomiques du bundle.

Cette structure remplace les deux catalogues séparés proposés auparavant. Deux Agrégats distincts ne pourraient pas garantir synchroniquement un invariant traversant leurs frontières ; à défaut d’un bundle unique, la cohérence devrait être explicitement externe et validée au build.

## 5. Adaptateur

`{id, version}` ne démontre pas à lui seul une Entité.

- **AdapterId** : identité logique du type d’Adaptateur, par exemple `cursor`.
- **AdapterRelease** : Objet-Valeur `{id, version, compatibilité, manifest/hash}`.
- **AdapterInstallation** : Entité du contexte Distribution si son cycle de vie installé/mis à jour/désinstallé doit être suivi dans un projet.
- **Adapter Runtime** : composant ou service d’application traduisant et exécutant les contrats ; il n’est pas nécessairement un objet du modèle persistant.

## 6. Conséquence pour l’audit

Les événements de handoff ou les preuves doivent référencer les révisions exactes exécutées. `event.details` peut techniquement les contenir, mais une structure dédiée et validée est préférable.

## 7. Limites

- Aucun bundle ni historique de révisions n’existe dans le dépôt actuel.
- Le choix entre référence durable et snapshot complet doit être testé selon taille, confidentialité et durée de conservation.
- La continuité métier de RoleId et le cycle de vie d’AdapterInstallation restent des décisions prospectives à confirmer par les cas d’usage.

## Sources

`.ai-team/schemas/event.schema.json`, `work-unit.schema.json`, Documents 2, 3, 5 et 7 corrigés, DDD Reference d’Eric Evans.
