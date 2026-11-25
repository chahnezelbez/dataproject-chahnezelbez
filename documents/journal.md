# Journal d’équipe

**Membres :** à renseigner. **Dépôt étudiant :** à renseigner.
Le journal retrace des décisions et résultats, pas une liste de commandes copiées.
Le remplir au fil du travail en quelques lignes par étape, sans y placer de **secret**.

## 1. Travail et alternance des rôles

| Séance/étape | Pilote | Observateur | Travail réellement réalisé | Commit/preuve | Difficulté | Prochaine action |
|---|---|---|---|---|---|---|
| À renseigner | Membre | Membre | Résultat concret | Référence | Symptôme | Action ciblée |

Faire apparaître les changements de rôles et les revues. Chaque membre doit
pouvoir expliquer une décision de développement et une décision d’exploitation.

## 2. Raisonnement lors d’un blocage

- Contexte et **résultat attendu** : à renseigner.
- Observation exacte, sans **secret** : à renseigner.
- Hypothèse et vérification choisie : à renseigner.
- Résultat de la vérification : à renseigner.
- Correction et contrôle de reprise : à renseigner.
- Leçon utile pour le **runbook** : à renseigner.

Une hypothèse infirmée reste utile : noter pourquoi elle a été abandonnée.

## 3. Revues et compréhension individuelle

| Élément relu | Auteur | Relecteur | Question posée | Correction/décision | Preuve de contrôle |
|---|---|---|---|---|---|
| À renseigner | Membre | Membre | Point précis | Résultat | Référence |

Vérifier aussi les commentaires : sont-ils cohérents avec le code réalisé ?
Supprimer les TODO terminés et conserver ceux qui décrivent un travail restant.

## 4. Usage d’outils d’IA

Indiquer l’aide obtenue, les adaptations et les vérifications effectuées.

| Besoin d’aide | Proposition reçue | Adaptation faite par l’équipe | Vérification | Limite ou proposition rejetée |
|---|---|---|---|---|
| À renseigner | Résumé, sans données privées | Modification comprise | Test/preuve | Explication |

Le binôme reste responsable de ce qu’il remet et doit pouvoir l’expliquer.
Un bloc généré ne devient pas valide sans lecture du contrat et contrôle réel.

## 5. Bilan final

Chaque membre indique une **règle métier** comprise, un incident diagnostiqué,
une décision d’infrastructure expliquée et un point qu’il approfondirait ensuite.

## Exemple de note utile à compléter

- Étape : accès **PostgreSQL** depuis l’API conteneurisée.
- Hypothèse à vérifier : le DSN utilise encore l’adresse du poste.
- Vérification choisie : comparer l’hôte configuré au contexte réseau, sans publier le DSN.
- **Observation :** à renseigner après lecture des éléments utiles.
- Correction et contrôle : à renseigner avec votre action et le résultat de **readiness**.
- Commit ou preuve : à renseigner si une modification a été nécessaire.

Cet exemple décrit une démarche, pas un incident déjà constaté par votre binôme.
Une difficulté résolue sans changement de code peut être documentée dans le journal
et le **runbook** sans inventer un **commit** de correction.
