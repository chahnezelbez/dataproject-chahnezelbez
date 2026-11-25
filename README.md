# Kit de départ CampusData

Ce dossier est un **starter pédagogique**, pas l'application terminée. CampusData ingère des fichiers CSV de mesures de qualité de l'air (CO₂, température, humidité) et calcule des indicateurs par salle. Les routes métier, le worker d'ingestion et l'**interface** sont à réaliser en séance 2 selon l'énoncé. Les configurations d'infrastructure sont fournies pour être adaptées, exécutées et expliquées.

## Utilisation

1. Copier tout le dossier dans un **dépôt étudiant** distinct, fichiers cachés compris.
2. Lire l'énoncé et la préparation dans le support de cours.
3. Générer `.env`, créer le **venv** Python 3.12 et installer `api/requirements-dev.lock`.
4. S1 : démarrer **PostgreSQL** avec `compose.dev.yaml`, lancer le socle API sur le poste.
5. S2 : développer `models`, `schemas`, `services`, `routes`, `database`, `init_db`, `ingestion` et `worker`, puis l'interface et les tests avec les fichiers de `data/`.
6. S3 : utiliser `compose.yaml` avec API, worker et web conteneurisés.
7. S4 : appliquer les manifestes Kubernetes, dont le CronJob d'ingestion, après import des images dans k3d.
8. S5 : publier les images et créer un overlay cloud pointant vers leurs digests.
9. S6 : copier `github-workflows/ci.yaml` dans `.github/workflows/ci.yaml` et l'adapter aux **tests métier** ; rédiger le README final à partir de `documents/readme-livraison.md`.

## Ce qui fonctionne dès le départ

- `/health/live` : santé du processus.
- `/health/ready` : connexion **PostgreSQL** uniquement ; ajouter le contrôle des trois tables en S2.
- `/api/version` : `dev` hors **image** ou version écrite au build.
- Deux tests de socle : ils ne valident ni l'API métier, ni l'ingestion.
- Trois fichiers CSV fictifs dans `data/` : un fichier valide (63 mesures), un fichier mêlant lignes valides, invalides et doublon, un fichier à l'en-tête invalide.
- **Images**, réseau et manifestes de support, sous réserve des outils et du registre disponibles.

## Travail à réaliser

- Modèles Dataset, Ingestion et Measurement, contrat **Pydantic**, transactions et cycle de vie des dépôts.
- Lecture et contrôle du CSV, insertion idempotente, rapport de rejets et indicateurs par salle.
- **Worker** `python -m app.worker` (boucle) et `--once` (un passage, utilisé par le CronJob).
- **Initialisation explicite** `python -m app.init_db` ; ce module n'existe volontairement pas encore.
- **Interface**, états d'erreur et **tests métier** sur PostgreSQL dédié.
- Configuration réelle, documentation, preuves et exploitation.

## Repères de configuration

| Contexte API | Hôte DB | Base | Point d’entrée navigateur |
|---|---|---|---|
| API sur le poste (S1-S2) | `127.0.0.1` | `campus` | `http://127.0.0.1:8080` via `web/dev.conf` |
| Tests sur le poste | `127.0.0.1` | `campus_test` | Aucun : pytest appelle l’API dans le processus |
| Compose (S3) | `db` | `campus` | `http://127.0.0.1:8080` |
| **Kubernetes** k3d (S4) | `db` | `campus` | `http://127.0.0.1:8081` |
| K3s sur EC2 (S5-S6) | `db` | `campus` | `http://127.0.0.1:8082` par tunnel SSH |
| CI | `localhost` | `campus_test` | Aucun |

La page « Aide-mémoire » du support de cours regroupe ports, variables et commandes de contrôle de chaque environnement.

Les tags des **images** de base servent au démarrage pédagogique ; relever et figer les **digests** pour la promotion. Les locks Python sont inclus. `pyproject.toml` fixe les règles Ruff et permet à pytest de résoudre le package `app` depuis la racine ou depuis `api/`. Régénérer les locks ensemble après une modification de dépendance, puis vérifier installation et tests.

## Secrets et fichiers générés

`.env.example` contient des placeholders. `.env`, dumps, clés et kubeconfigs sont ignorés par Git. Ne jamais publier les valeurs réelles dans les documents. Ne pas utiliser `docker compose down -v` ou supprimer un **PVC** avant d'avoir sauvegardé les données utiles.

Les modèles `documents/` sont à compléter au fil des séances. Après réalisation, remplacer ce README de starter par votre README opérationnel, tout en indiquant les modèles reçus et le travail de l'équipe.

## Lire les modèles dans un ordre utile

Les commentaires expliquent les intentions, les dépendances et les limites.
Ils ne remplacent pas la vérification du comportement après adaptation.

| Fichier ou groupe | À comprendre avant modification | Travail étudiant | **Preuve attendue** |
|---|---|---|---|
| `api/app/main.py` | Engine, probes et fichier VERSION | Extraire l’accès DB, compléter **readiness**, inclure les routes métier | Routes et santé conformes |
| `api/tests/test_health.py` | Tests dans le processus, sans réseau réel | Ajouter **tests métier** et isolation **PostgreSQL** | Résultats et état DB vérifiés |
| `api/requirements*.in` et locks | Dépendances directes et versions résolues | Conserver les locks cohérents | Installation reproductible |
| `api/Dockerfile` | Build/runtime, wheels, utilisateur, version | Expliquer et adapter les fichiers nécessaires | UID, **image** et version observés |
| `api/.dockerignore` | Contexte API et exclusions | Vérifier les fichiers entrant au build | Aucun **secret** dans le contexte |
| `web/index.html` | Structure, labels, messages, chargement JS | Créer formulaires et interactions | Parcours clavier et états UI |
| `web/app.js` | Plan de réalisation et **contrat HTTP** | Implémenter requêtes, rendu et mutations | 204/422/409/réseau gérés |
| `web/styles.css` | Lisibilité, focus et états | Compléter sans masquer le focus | Affichage lisible et utilisable |
| `web/dev.conf` | API sur le poste via le proxy conteneurisé | Vérifier le chemin de développement | **Même origine** en S2 |
| `web/default.conf` et **Dockerfile** | API interne et fichiers embarqués | Inclure tous les assets livrés | Rendu et appels API dans l’**image** |
| `compose.dev.yaml` | DB/proxy en **conteneurs**, API locale | Adapter l’environnement local | DB accessible sur le poste |
| `compose.yaml` | Quatre services (db, api, worker, web), santé, ports et **volume** | Valider ordre d’initialisation et reprise | Témoin persistant |
| `.env.example` et `.gitignore` | Placeholders et fichiers non versionnés | Générer les valeurs réelles **hors Git** | Revue avant **commit** |
| `k8s/00-namespace.yaml` | Périmètre des objets | Vérifier le contexte cible | **Namespace** correct |
| `k8s/10-config.yaml` | Configuration non secrète | Créer le **Secret** séparément | Références cohérentes |
| `k8s/20-db.yaml` | **PVC**, serveur unique et Recreate | Expliquer stockage et interruption | Donnée après remplacement |
| `k8s/30-api.yaml` | **Réplicas**, droits, probes et ressources | Vérifier comportement de santé réalisé en S2 | **Réconciliation** et disponibilité |
| `k8s/35-worker.yaml` | CronJob, `--once`, concurrence interdite | Vérifier l'image et le Secret ; observer un Job | Dépôt `pending` traité en moins de 2 min |
| `data/*.csv` | Format attendu et cas d'erreur | Utiliser ces fichiers dans les tests et la recette | Compteurs conformes au contrat |
| `k8s/40-web.yaml` | **Image** web et **Service** | Contrôler fichiers et réseau | Page puis dépôt et indicateurs réussis |
| `k8s/50-ingress.yaml` | Routage vers web par Traefik | Vérifier l’entrée locale/cloud | Accès au point prévu |
| `k8s/kustomization.yaml` | Assemblage des ressources | Créer l’overlay cloud en S5 | **Images** finales par **digest** |
| `github-workflows/ci.yaml` | Dépendances des jobs et conditions de publication | Déplacer au bon chemin, initialiser DB, tester le métier | Run et **images** traçables |
| `pyproject.toml` | Découverte des tests et règles Ruff | Exécuter les contrôles depuis le projet étudiant | Lint et pytest réussis |
| `documents/` | Trames à compléter, pas résultats déjà validés | Rédiger tout au long des séances | Dossier reproductible et honnête |
| `documents/readme-livraison.md` | Rubriques du README final exigées en S6 | Remplacer ce README de starter en S6 | README suivi par une autre équipe |

## Transformer un TODO en réalisation vérifiée

1. Retrouver la règle dans le **contrat commun** et un exemple positif/négatif.
2. Identifier le fichier responsable ; ne pas placer toute la logique dans main.py.
3. Écrire la plus petite opération qui respecte ce contrat et les erreurs attendues.
4. Ajouter la vérification observable ; relire les données après une mutation refusée.
5. Intégrer avec le composant voisin, puis réaliser le parcours utilisateur.
6. Remplacer le TODO terminé par un commentaire d’intention si nécessaire.
7. Consigner **commit**, résultat et limite dans la recette.

Le kit ne contient volontairement pas `models.py`, `schemas.py`, `services.py`,
`routes.py`, `database.py`, `init_db.py`, `ingestion.py` ni `worker.py`. Ces fichiers sont à produire en S2 : la page de la séance 2 donne, pour chacun, du code de départ testé, les parties `TODO` à écrire et une solution à consulter en cas de blocage.
Les commandes d’initialisation des séances suivantes ne fonctionneront qu’après
leur réalisation. Ne pas masquer leur absence avec un script vide qui retourne 0.

## Commenter sans rendre le code illisible

Placer le commentaire près de la décision qu’il explique. Préférer une phrase
sur l’invariant à dix lignes décrivant chaque affectation. Pour les fonctions
importantes, une docstring décrit rôle, résultat et erreurs significatives.
Dans YAML, expliquer les liens entre champs et les hypothèses du laboratoire.

Exemples de questions auxquelles vos commentaires doivent répondre :

- Pourquoi une **Session par requête** et une fermeture même en cas d’erreur ?
- Pourquoi un même fichier déposé deux fois ne doit-il pas créer de doublons ?
- Pourquoi le worker verrouille-t-il le dépôt avec SKIP LOCKED ?
- Pourquoi la **liveness** ne consulte-t-elle pas **PostgreSQL** ?
- Pourquoi le volume DB doit-il survivre au conteneur ?
- Pourquoi un Pod Running peut-il être non prêt ?
- Pourquoi un pipeline réussi ne déploie-t-il pas automatiquement la VM ?

Ne placer aucune valeur secrète dans un commentaire. Un commentaire est du texte
versionné et parfois embarqué dans l’**image**, comme le code qu’il accompagne.

## Lire les commentaires de prise en main

Les fichiers modifiables indiquent **CONTEXTE ÉTUDIANT**, **À PRÉPARER / ADAPTER**
ou **À RÉALISER**, puis **CONTRÔLE ATTENDU**. Lisez ces trois indications avant
modification : elles distinguent le rôle du fichier, votre travail et la preuve
à produire. Les commentaires sont conservables dans votre dépôt.

Les fichiers requirements.lock et requirements-dev.lock sont générés : leurs
commentaires d’origine et leurs lignes via décrivent la résolution des dépendances.
Ne les annotez pas en modifiant des versions au hasard. Vos intentions de changement
se documentent dans les fichiers .in et dans votre journal, puis vous régénérez
les deux locks selon la préparation.

Les trames documents/ proposent des exemples de rédaction explicitement à
compléter. Une observation laissée « à renseigner » n’est pas une validation.
Lorsque vous rédigez vos propres procédures, commentez aussi terminal, dossier,
variables attendues et effet des commandes : votre README doit rester utilisable
par une personne qui vient d’ouvrir son terminal.
