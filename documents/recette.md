# Rapport de recette

**Équipe :** à renseigner. **Date :** à renseigner. **Exécutant/relecteur :** à renseigner.
**Commit applicatif :** à renseigner. **Digests API/web :** à renseigner si construits.
**Contexte de déploiement et commit de configuration :** à renseigner.

## 1. Conditions d’exécution

Préciser poste ou VM, versions utiles, **base dédiée**, données de départ et
**préconditions**. Ne jamais inscrire mot de passe, DSN complet, clé ou kubeconfig.
Les **tests d’intégration** utilisent une base se terminant par _test ; décrire
la stratégie de nettoyage et sa protection avant toute suppression.

## 2. Résultats par exigence

| ID du référentiel | **Préconditions** | Action / commande | Attendu | Observé | Preuve | Résultat |
|---|---|---|---|---|---|---|
| À reprendre du **barème** | État initial | Action reproductible | Contrat | Constat réel | Fichier/lien | Statut |

Résultats autorisés : validé, échoué, **non exécuté**, **non applicable avec justification**.
Ne jamais remplacer une observation par le **résultat attendu**. Si une commande
n’a pas été lancée, indiquer non exécuté même si sa syntaxe paraît correcte.

## 3. Exemple de rédaction d’un cas

**Exemple méthodologique à exécuter, pas résultat déjà obtenu :**

- **Précondition :** jeu de données créé, fichier `data/mesures-salles-2026-10-05.csv` déjà ingéré (63 mesures).
- **Action :** déposer le même fichier une seconde fois, puis lancer le worker.
- **Attendu :** dépôt `succeeded` avec 0 acceptée et 63 doublons ; `measurement_count` **toujours égal à 63 à la relecture**.
- **Observé :** à compléter après exécution.
- **Preuve :** requête, réponse et lecture suivante dans le même environnement.
- **Conclusion :** à compléter ; une assertion sur le seul statut `succeeded` est insuffisante.

## 4. Expériences de déploiement et de reprise

Pour chaque expérience, conserver identifiants et données avant/après :

- **Persistance** Compose : UUID témoin et **volume** conservé après recréation.
- **Réconciliation** API : Pod précédent/remplaçant et états prêts observés.
- **Panne DB :** liveness, readiness, requêtes métier et reprise.
- **Cloud :** version, contexte VM et références d’images cohérents.
- **Rollback :** ancienne release API et web effectivement retrouvée.
- **Restauration :** base cible distincte, UUID/contenu retrouvé et durée mesurée.

Indiquer les erreurs transitoires et les limites de chaque expérience.
Un tableau de résultats n’oblige pas à conclure que tout a fonctionné.

## 5. Anomalies connues

| ID | Reproduction minimale | Attendu/observé | Impact | Priorité | Correction ou contournement | État |
|---|---|---|---|---|---|---|
| À renseigner | Données et étapes | Écart précis | Utilisateur/technique | Justification | Action | Ouvert/clos |

Une correction est clôturée après un nouveau contrôle du scénario affecté.
Relier le résultat à son **commit** pour éviter d’attribuer une ancienne preuve
à une version plus récente non testée.

## 6. Synthèse de remise

Lister critères validés, écarts restants, opérations non exécutées et limites.
Indiquer où trouver les preuves expurgées et quelle version le jury doit évaluer.

## Comment annoter une preuve

Donnez un nom explicite à chaque sortie conservée : séance, scénario et version.
Convention commune du support : `proofs/sN-sujet.ext`, par exemple
`proofs/s3-persistance.txt`, `proofs/s4-reconciliation.txt`,
`proofs/s6-overlay-s5.yaml` ou `proofs/latence-k3d.json`. Les fichiers privés
(dump, sorties non expurgées) vont uniquement dans `proofs/private/`, ignoré par Git.
Ajoutez une phrase qui indique ce que le lecteur doit observer. Exemple de forme :
« Sur la réponse de relecture, comparer l’identifiant du jeu, son nombre de mesures et sa somme de contrôle à ceux relevés avant
la recréation. » Complétez ensuite avec vos valeurs et votre **résultat réel**.

N’utilisez pas un exemple du cours comme **résultat observé**. Expurgez les secrets,
mais conservez les statuts, identifiants de jeux de données fictifs et messages utiles
pour comprendre le scénario.
