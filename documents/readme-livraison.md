# Trame du README opérationnel - à renseigner

En séance 6, ce contenu remplace le `README.md` du starter à la racine de votre
dépôt. Il s’adresse à une personne qui n’a assisté à aucune séance : elle doit
pouvoir installer, vérifier, mettre à jour, restaurer et nettoyer sans oral.
Supprimer les consignes en italique une fois la rubrique rédigée.

**Équipe :** à renseigner. **Commit décrit :** à renseigner.
**Release évaluée (images API/web par digest) :** à renseigner.

## 1. Besoin et architecture

_Trois à cinq phrases sur le besoin, puis le schéma navigateur - Nginx - API -
PostgreSQL avec le stockage durable. Lien vers `documents/architecture.md`._

## 2. Limites connues du prototype

_Pas d’authentification, un nœud, une DB à un réplica, stockage local, accès par
tunnel. Ajouter les anomalies ouvertes de `documents/recette.md`._

## 3. Prérequis

| Outil ou accès | Version vérifiée | Commande de contrôle |
|---|---|---|
| Python | À relever | `python3.12 --version` |
| Docker / Compose | À relever | `docker version`, `docker compose version` |
| k3d / kubectl | À relever | `k3d version`, `kubectl version --client` |
| Compte AWS et GHCR | Région, droits | Voir préparation |

## 4. Procédures

Chaque procédure suit le même format. Ne jamais écrire de secret dans ce fichier.

| Rubrique | Lieu (poste/VM/conteneur) | Dossier de départ | Prérequis et variables | Commandes | Résultat attendu | Diagnostic si échec |
|---|---|---|---|---|---|---|
| Générer `.env` | Poste | Racine | Aucun `.env` existant | À renseigner | Fichier 600 ignoré par Git | `git check-ignore .env` |
| Développement local | Poste | Racine puis `api/` | `.env`, venv | À renseigner | live/ready 200 | À renseigner |
| Tests isolés | Poste | Racine puis `api/` | DSN vers `campus_test` | À renseigner | Nombre de tests réussis | À renseigner |
| Initialisation du schéma | Selon environnement | À renseigner | DB prête | À renseigner | Deux exécutions sans perte | À renseigner |
| Compose complet | Poste | Racine | `.env` rechargé (`db`) | À renseigner | Pile saine, dépôt traité par le worker | À renseigner |
| Kubernetes local | Poste | Racine | Contexte `k3d-campusdata` | À renseigner | 2 API Ready, PVC Bound | À renseigner |
| Publication des images | Poste ou CI | Racine | Connexion GHCR | À renseigner | Deux digests relevés | À renseigner |
| Déploiement cloud | VM | `~/campusdata` | Fonction `kubectl`, Secret | À renseigner | Version attendue servie | À renseigner |
| Tunnel SSH | Poste | Indifférent | `CAMPUS_KEY`, `CAMPUS_HOST` | À renseigner | Page sur 8082 | À renseigner |
| Mise à jour (promotion) | Poste puis VM | Racine / `~/campusdata` | Run CI vert, digests | À renseigner | Rollout terminé, version | À renseigner |
| Rollback | Poste puis VM | Racine / `~/campusdata` | Overlay précédent conservé | À renseigner | Ancienne version, données | À renseigner |
| Sauvegarde | VM puis poste | `~` / racine | Jeu témoin relevé (id, nombre de mesures) | À renseigner | Dump non vide hors VM | À renseigner |
| Restauration | VM | `~` | Dump disponible | À renseigner | Témoin identique dans `campus_restore` | À renseigner |
| Nettoyage | Console AWS, poste | - | Preuves exportées | À renseigner | Inventaire vide ou exceptions | À renseigner |

## 5. Preuves et recette

_Lien vers `documents/recette.md`, dossier `proofs/` et convention de nommage.
Indiquer quelles preuves correspondent à la release évaluée._

## 6. Travail fourni et travail de l’équipe

_Lister les modèles reçus du kit, ce que l’équipe a écrit ou adapté, et les
aides extérieures déclarées dans `documents/journal.md`._
