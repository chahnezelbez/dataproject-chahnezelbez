"use strict";
// CONTEXTE ÉTUDIANT : S2, script chargé par index.html dans le navigateur.
// À RÉALISER : remplacer le plan ci-dessous par vos fonctions et événements.
// CONTRÔLE : onglet Réseau pour HTTP, Console pour JS, puis recette au clavier.
// Les secrets PostgreSQL et les clés cloud n’ont aucune place dans ce fichier.

/*
 * Atelier S2 : construire l'interface à partir du contrat, sans bibliothèque.
 * Ce fichier est volontairement un plan de réalisation, pas un corrigé.
 * Les noms proposés ci-dessous sont des suggestions, pas une API imposée.
 *
 * 1. request(path, options)
 *    Appeler fetch avec un chemin relatif (/api/datasets) pour conserver l'origine.
 *    JSON : envoyer Content-Type: application/json. Fichier CSV : envoyer le
 *    File tel quel comme body avec Content-Type: text/csv (pas de FormData).
 *    Traiter 204 avant response.json() : la suppression n'a pas de corps.
 *    Contrôler response.ok : fetch ne rejette pas sur 404, 409, 413, 415 ou 422.
 *    detail peut être une chaîne ou une liste ; un proxy peut renvoyer du HTML.
 *
 * 2. Jeux de données : loadDatasets() et renderDatasets(datasets)
 *    Afficher chargement, liste vide, liste ou erreur sans les confondre.
 *    Construire les éléments DOM et écrire les données avec textContent.
 *    Ne jamais injecter name, owner ou description dans innerHTML.
 *    Suppression : confirmation affichant le nom ; une annulation n'envoie rien.
 *
 * 3. Dépôt d'un fichier : POST /api/datasets/{id}/ingestions?filename=...
 *    La réponse 202 signifie « reçu et en attente », pas « traité ».
 *    Afficher le statut pending, puis interroger GET /api/ingestions/{id}
 *    toutes les 2 secondes jusqu'à succeeded ou failed (arrêter le suivi
 *    après un nombre borné d'essais et le dire à l'utilisateur).
 *    Désactiver le bouton pendant l'envoi, le réactiver dans finally.
 *
 * 4. Rapport et relance
 *    Afficher rows_accepted, rows_rejected, rows_duplicate et les premières
 *    erreurs de ligne (numéro + raison). Un dépôt failed propose « Relancer »
 *    (POST /api/ingestions/{id}/retry) ; les autres statuts ne le proposent pas.
 *
 * 5. Indicateurs : GET /api/datasets/{id}/stats?room=&from=&to=
 *    Tableau par salle : mesures, CO2 moyen/min/max, température et humidité
 *    moyennes, dernière mesure. Les dates saisies deviennent des dates ISO
 *    avec fuseau ; une période invalide (from > to) produit un message lisible.
 *
 * 6. Recette manuelle
 *    Tester au clavier, avec liste vide, fichier invalide et API indisponible.
 *    Créer un jeu nommé « Salles <b>A</b> » : les balises s'affichent en texte.
 *    Ajouter la version API dans l'interface pour la recette cloud.
 */
