# AGENTS.md — CampusData

Sources de vérité : `SPEC_PROJET.md` et `README.md` (le détail des US est repris de `documents/architecture.md`). En cas de divergence, les sources prévalent. Ce fichier ne crée aucune contrainte supplémentaire.

## 1. Périmètre

- Kit de départ pédagogique, **pas l'application terminée**. CampusData ingère des CSV de mesures de qualité de l'air (CO₂, température, humidité) et calcule des indicateurs par salle.
- Projet en **binôme**, **6 séances de 3 h**, version du 17 novembre 2026.
- Mission : créer une application web puis la faire tourner dans quatre environnements de plus en plus proches de la production : poste, Docker, Kubernetes, AWS.
- À produire en S2 : `models`, `schemas`, `services`, `routes`, `database`, `init_db`, `ingestion`, `worker`, interface et tests métier. Le kit ne contient volontairement aucun de ces modules Python. Ne pas masquer leur absence avec un script vide qui retourne 0.
- Les mesures sont fictives ; trois fichiers sont fournis dans `data/` : `mesures-salles-2026-10-05.csv` (63 mesures), `mesures-avec-erreurs.csv` et `en-tete-invalide.csv`.

## 2. Architecture exacte

### Découpage imposé

```
api/app/
├── main.py           # composition des routes, probes, version
├── database.py       # engine, Base, sessions et dépendance get_session
├── models.py         # tables datasets, ingestions, measurements et contraintes
├── schemas.py        # DatasetCreate, DatasetRead, IngestionRead, StatsRead
├── services.py       # cas d'utilisation : jeux, dépôts, relance, indicateurs
├── ingestion.py      # lecture du CSV et contrôles qualité, sans accès HTTP
├── worker.py         # boucle et --once : prise en charge et traitement des dépôts
├── routes.py         # HTTP, paramètres, codes et traduction d'erreurs
└── init_db.py        # création initiale explicite du schéma
```

Responsabilités et interdictions :

- La **route** valide la requête, appelle le service, forme la réponse ; elle ne contient ni SQL ni lecture CSV.
- Le **service** charge, vérifie la règle, applique la mutation atomique ; il ne dépend ni du DOM ni d'une URL navigateur.
- `ingestion.py` transforme un texte CSV en lignes valides et en rapport d'erreurs ; il n'ouvre pas de session et ne connaît pas FastAPI. Il reste pur pour être testé sans base.
- Le **worker** prend un dépôt, appelle `ingestion.py`, insère et conclut ; il n'est pas lancé par le processus API.
- Une **Session** délimite une transaction, rollback si échec, fermeture systématique ; ce n'est jamais un objet global partagé entre requêtes.
- Le **frontend** affiche les états et appelle l'API ; il n'est pas la seule protection des règles métier.
- Aucune flèche de dépendance ne remonte de la base vers les routes.
- Fonctions synchrones `def` et SQLAlchemy synchrone suffisent pour ce volume. Ne pas mettre de SQL bloquant dans une fonction `async def` sans stratégie adaptée.
- Le corps du dépôt se lit brut via une dépendance `async def raw_body(request: Request) -> bytes: return await request.body()` utilisée par une route `def` : les contrôles 415, 413 et 422 « Empty file » sont ainsi faits dans l'ordre du contrat. Aucun upload multipart.
- `python -m app.init_db` importe les modèles puis appelle `Base.metadata.create_all(engine)`. Commande idempotente, exécutée explicitement une fois avant l'ouverture du trafic, pas au démarrage de chaque réplica API ni de chaque passage du worker. `create_all` ne fait pas évoluer une table existante : schéma gelé après S2, Alembic en extension.

### Modèle de données (3 tables)

- `DATASET ||--o{ INGESTION` et `DATASET ||--o{ MEASUREMENT`, `INGESTION ||--o{ MEASUREMENT` ; suppression d'un jeu en cascade (`ON DELETE CASCADE`).
- `datasets` : `id` UUID v4 généré serveur ; `name` VARCHAR(120) unique, espaces externes retirés, 3 à 120 caractères ; `description` TEXT nullable, ≤ 2 000 caractères ; `owner` VARCHAR(60) nettoyé, 2 à 60 caractères, défaut `Équipe` ; `created_at` TIMESTAMPTZ UTC généré serveur et immuable ; `measurement_count` entier calculé, non stocké.
- `ingestions` : `id` UUID v4 ; `dataset_id` FK cascade ; `filename` VARCHAR(255), 1 à 255 caractères, sans `/` ni `\` ; `status` VARCHAR(10) dans `pending`, `running`, `succeeded`, `failed`, initial `pending` ; `content` BYTEA, octets bruts ≤ 1 Mio, **jamais renvoyé par l'API** (BYTEA et non TEXT : un fichier non UTF-8 doit pouvoir être stocké pour être refusé par le worker) ; `rows_total`, `rows_accepted`, `rows_rejected`, `rows_duplicate` INTEGER null jusqu'au traitement ; `errors` JSONB, au plus 20 objets `{"line": n, "reason": "..."}`, initial `[]` ; `error_message` TEXT nullable ; `created_at`, `started_at`, `finished_at` TIMESTAMPTZ, les deux derniers posés par le worker, remis à `null` lors d'une relance.
- Invariant d'un dépôt réussi : `rows_total = rows_accepted + rows_rejected + rows_duplicate` (une contrainte `CHECK` peut le garantir pour `succeeded`).
- `measurements` : `id` BIGINT identité technique non exposé ; `dataset_id` et `ingestion_id` UUID FK cascade ; `room` VARCHAR(30), 1 à 30 caractères après retrait des espaces ; `measured_at` TIMESTAMPTZ ; `co2_ppm` INTEGER `CHECK` 250–10 000 ; `temperature_c` NUMERIC(4,1) `CHECK` −30–60 ; `humidity_pct` NUMERIC(4,1) `CHECK` 0–100.
- Contrainte `UNIQUE (dataset_id, room, measured_at)` : elle rend l'ingestion idempotente et sert d'index aux indicateurs. Ajouter un index sur `ingestions (status, created_at)` pour le worker, en expliquant son coût à l'écriture. Les contraintes SQL protègent les écritures hors API ; les contrôles du worker donnent un rapport lisible : les deux sont nécessaires.
- Volume pédagogique < 100 000 mesures ; pas de pagination dans le socle.

Présence / absence à la création d'un jeu (base des tests F01–F05) :

| Champ | Absent | `null` | Chaîne vide ou espaces |
|---|---|---|---|
| `name` | 422 | 422 | 422 |
| `description` | `null` | accepté (`null`) | acceptée telle quelle |
| `owner` | `Équipe` | 422 | 422 |
| `id`, `created_at`, `measurement_count` | générés | 422 (champ inconnu) | 422 (champ inconnu) |

Refuser les champs inconnus avec `extra="forbid"`. L'interface envoie `null` pour une description vide.

Horodatages : stockage TIMESTAMPTZ, réponse UTC (`…Z`). Le worker pose `started_at` à la prise en charge et `finished_at` à la fin, réussite ou échec ; une relance remet les deux à `null`. Un instant du fichier `2026-10-05T09:00:00+02:00` est enregistré `2026-10-05T07:00:00Z`.

### Cycle de vie et worker

- États : dépôt accepté (202) → `pending` → `running` (worker) → `succeeded` ou `failed` ; `failed` → `pending` sur relance ; `succeeded` → fin. Le client ne choisit jamais de statut et il n'existe pas de route de modification directe.
- Relance : `failed` → 200 avec compteurs, `errors` et dates remis à zéro ; `pending`/`running`/`succeeded` → 409, aucune mutation.
- `python -m app.worker` boucle et attend `WORKER_INTERVAL_SECONDS` (5 s par défaut) sans dépôt ; `python -m app.worker --once` traite tous les dépôts en attente puis sort avec le code 0 (forme utilisée par le CronJob).
- Algorithme : transaction 1 `SELECT … FROM ingestions WHERE status = 'pending' ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED`, passage à `running` + `started_at`, COMMIT ; transaction 2 décodage, en-tête, contrôle des lignes, `INSERT … ON CONFLICT (dataset_id, room, measured_at) DO NOTHING`, compteurs, `errors`, `succeeded`, `finished_at`, COMMIT ; si refus ou exception : ROLLBACK de la transaction 2 puis transaction 3 `failed`, `error_message`, `finished_at`, COMMIT.
- `SKIP LOCKED` permet deux workers concurrents sans traiter le même dépôt. `rows_duplicate` = lignes valides − lignes réellement insérées (comptées avec `RETURNING`). `error_message` reste générique : ni DSN ni mot de passe.
- Base indisponible : en boucle, journaliser puis attendre l'intervalle et réessayer sans s'arrêter ; avec `--once`, code non nul et le Job Kubernetes réessaie (`backoffLimit`). Aucun dépôt `pending` n'est perdu.
- Limite à documenter : un arrêt brutal en plein traitement laisse le dépôt `running` ; la remise automatique en `pending` après 10 min est une extension.

### Indicateurs et interface

- `GET /api/datasets/{id}/stats` agrège en SQL (`GROUP BY room`, `count`, `avg`, `min`, `max`), trié par nom de salle ; jamais de chargement de toutes les mesures en Python. Filtres facultatifs `room` (égalité exacte), `from` (inclus), `to` (exclu), dates ISO 8601 avec fuseau. `from >= to` donne 422. Moyennes arrondies à une décimale ; sans mesure : `rooms: []`.
- Quatre états par liste : chargement, liste vide, données visibles, erreur. Un dépôt accepté affiche d'abord `pending` : 202 signifie « reçu », pas « traité ». Suivi jusqu'à `succeeded`/`failed` avec nombre d'essais borné (interrogation toutes les 2 s, au plus 60 fois). Pendant une mutation, désactiver le bouton et le réactiver dans un `finally`.
- Suppression d'un jeu : confirmation affichant son nom et le nombre de mesures supprimées. Chaque champ a un `<label>`, les boutons sont accessibles au clavier, les tableaux ont un `<caption>` et des `<th scope="col">`. Affichage avec `textContent`, jamais d'interpolation dans `innerHTML`.

## 3. Réseau et environnements

| Environnement | Navigateur → web | web → API | API et worker → DB | Worker |
|---|---|---|---|---|
| Développement | `127.0.0.1:8080` | `host.docker.internal:8000` | `127.0.0.1:5432` depuis le poste | `python -m app.worker --once` dans un terminal |
| Compose complet | `127.0.0.1:8080` | `api:8000` | `db:5432` | service `worker` en boucle |
| Kubernetes local (k3d) | `127.0.0.1:8081` via Ingress | Service `api:8000` | Service `db:5432` | CronJob `ingest`, toutes les minutes |
| Cloud avec tunnel | `127.0.0.1:8082` | SSH | Service `api:8000` / `db:5432` | CronJob `ingest`, toutes les minutes |

Repères complémentaires : API locale S1–S2 → hôte DB `127.0.0.1`, base `campus` ; tests sur le poste → `127.0.0.1`, `campus_test`, pytest appelle l'API dans le processus ; Compose → `db`, `campus`, `http://127.0.0.1:8080` ; k3d → `db`, `campus`, `http://127.0.0.1:8081` ; K3s EC2 → `db`, `campus`, `http://127.0.0.1:8082` par tunnel SSH ; CI → `localhost`, `campus_test`.

- Dans le navigateur, `fetch('/api/datasets')` garde la **même origine**. `http://api:8000` est un nom interne : le navigateur ne sait pas le résoudre. `localhost` dans un conteneur désigne ce conteneur, pas le posté ni PostgreSQL.
- Le worker n'expose aucun port : il ne reçoit pas de requêtes, il interroge la base. Seul `web` est publié (8080). La DB n'est pas publiée.
- L'API expose toutes ses routes sous `/api` dans tous les environnements ; Nginx transmet ce préfixe sans le retirer.
- Variables secrètes injectées à l'exécution : `.env` pour Compose, Secret Kubernetes partagé par l'API et le CronJob. L'encodage base64 d'un Secret ne le rend pas sûr : accès au cluster, stockage et droits doivent être protégés.
- Reproductibilité : démarrage sans édition de code entre Compose et Kubernetes. Les tags des images de base servent au démarrage pédagogique ; figer les **digests** pour la promotion. Locks Python inclus et régénérés ensemble après changement de dépendance.

### Kafka : non documenté dans les sources

Ni `SPEC_PROJET.md` ni `README.md` (ni le reste du kit examiné) ne mentionne Kafka. L'intégration documentée est **HTTP/JSON + PostgreSQL + worker/CronJob** ; aucun « choix d'intégrer Kafka » ne peut donc être consigné comme contrainte du projet sans rien inventer. Si l'équipe décide d'ajouter Kafka, ce sera une **extension explicite** à documenter dans `documents/architecture.md` (besoin, alternative, limite) et à valider avant de la traiter comme exigence ; elle ne remplace pas le contrat HTTP/PostgreSQL décrit ci-dessus.

## 4. Contrat HTTP

Toutes les réponses métier sont JSON, sauf la suppression 204 sans corps.

| Méthode | Route | Entrée | Succès | Échecs à gérer |
|---|---|---|---|---|
| GET | `/api/datasets` | — | 200, tableau trié par `created_at` décroissant puis `id` | 503 |
| POST | `/api/datasets` | `DatasetCreate` JSON | 201, `DatasetRead` | 422 ; 409 nom déjà utilisé ; 503 |
| GET | `/api/datasets/{id}` | UUID | 200, `DatasetRead` | 422 ; 404 ; 503 |
| DELETE | `/api/datasets/{id}` | UUID | 204 sans corps ; dépôts et mesures supprimés | 422 ; 404 ; 503 |
| POST | `/api/datasets/{id}/ingestions?filename=…` | corps `text/csv` | 202, `IngestionRead` `pending`, en-tête `Location` | 415 ; 413 ; 422 ; 404 ; 503 |
| GET | `/api/datasets/{id}/ingestions` | `status` facultatif | 200, tableau trié par `created_at` décroissant | 422 statut inconnu ; 404 ; 503 |
| GET | `/api/ingestions/{id}` | UUID | 200, `IngestionRead` | 422 ; 404 ; 503 |
| POST | `/api/ingestions/{id}/retry` | — | 200, `IngestionRead` `pending` | 422 ; 404 ; 409 statut non `failed` ; 503 |
| GET | `/api/datasets/{id}/stats` | `room`, `from`, `to` facultatifs | 200, indicateurs par salle | 422 période invalide ; 404 ; 503 |
| GET | `/api/version` | — | 200, `{"version":"<commit>"}` | pas d'accès DB |
| GET | `/health/live` | — | 200, `{"status":"ok"}` | ne dépend pas de PostgreSQL |
| GET | `/health/ready` | — | 200, `{"status":"ready"}` | 503 si DB ou l'une des trois tables indisponible |

- `IngestionRead` contient tous les champs du dépôt sauf `content` ; le contenu brut reste en base pour la relance.
- Erreurs : 404 `Dataset not found` / `Ingestion not found` ; 409 `Dataset name already exists` / `Ingestion cannot be retried` ; 503 `Database unavailable` ; 415 `Expected text/csv` ; 413 `File too large` ; 422 propre au contrat `Empty file` ou période invalide avec `detail` chaîne. Les 422 de validation FastAPI gardent `detail` sous forme de liste. Une panne inattendue donne 500 avec message générique, trace dans les logs ; ni DSN ni mot de passe exposés.
- Le frontend gère `detail` chaîne ou liste, et un corps non JSON.
- Ordre d'évaluation : validation des paramètres et du corps (422, 415, 413) → recherche de la ressource (404) → règle métier (409) → enregistrement. Un nom déjà utilisé est détecté par la contrainte `UNIQUE` : traduire l'`IntegrityError` en 409, pas toutes les erreurs SQL.
- Valeur de `/api/version` : `dev` hors image, sinon version écrite au build ; l'interface affiche la même valeur dans chaque environnement.

## 5. Règles de validation CSV

- Fichier texte UTF-8, séparateur virgule, en-tête exact sur la première ligne : `room,measured_at,co2_ppm,temperature_c,humidity_pct`.
- Contrôle de chaque ligne dans cet ordre ; la première règle violée donne la raison enregistrée dans `errors`. Les numéros sont ceux du fichier, en-tête = ligne 1.

| Ordre | Règle | Raison |
|---|---|---|
| 1 | Exactement 5 colonnes | `Expected 5 columns` |
| 2 | `room` : 1 à 30 caractères après retrait des espaces | `Invalid room` |
| 3 | `measured_at` : date ISO 8601 avec fuseau | `Invalid measured_at` |
| 4 | `measured_at` au plus 5 minutes dans le futur | `measured_at in the future` |
| 5 | `co2_ppm` : entier 250–10 000 | `Invalid co2_ppm` |
| 6 | `temperature_c` : nombre −30–60 | `Invalid temperature_c` |
| 7 | `humidity_pct` : nombre 0–100 | `Invalid humidity_pct` |

- La règle 4 dépend de l'heure de traitement : passer l'instant de référence en paramètre (`now`) dans les tests plutôt que lire l'horloge. Les fichiers du kit sont datés d'octobre 2026, sauf la ligne volontairement future (2030).
- Une ligne valide dont le couple (`room`, `measured_at`) existe déjà dans le jeu, ou apparaît plus haut dans le même fichier, compte comme **doublon** : ni insérée, ni erreur. Lignes vides ignorées et non comptées. Toutes les lignes rejetées comptent dans `rows_rejected`, mais seules les 20 premières sont détaillées dans `errors`.

Contrôles du fichier entier :

| Situation | Où | Résultat |
|---|---|---|
| Corps vide | API | 422 `Empty file`, aucun dépôt créé |
| Plus de 1 Mio (1 048 576 octets) | API | 413 `File too large`, aucun dépôt créé |
| `Content-Type` ≠ `text/csv` | API | 415 `Expected text/csv`, aucun dépôt créé |
| Contenu non UTF-8 | Worker | `failed`, `File is not valid UTF-8` |
| En-tête différent | Worker | `failed`, `Invalid header` |
| Aucune ligne de données | Worker | `failed`, `No data rows` |
| Plus de 10 000 lignes de données | Worker | `failed`, `Too many rows` |

Un dépôt `failed` n'insère aucune mesure : la transaction du traitement est annulée en entière.

## 6. User Stories US01–US10

| US | Énoncé | Critères essentiels | Contrôles |
|---|---|---|---|
| US01 | Créer un jeu de données pour regrouper des mesures | Nom unique ; doublon → 409 | F01–F05, F28 ; S2 |
| US02 | Lister et ouvrir les jeux pour savoir ce qu'ils contiennent | Nombre de mesures affiché ; jeu inconnu → 404 | F06, F07, F29, F30 ; S2 |
| US03 | Supprimer un jeu devenu inutile | Confirmation avec nom et nombre de mesures ; annulation → rien supprimé | F08, F09, F30 ; S2 |
| US04 | Déposer un CSV sans recopie manuelle | 202 + `pending` ; jeu absent → 404 | F10–F12, F28, F29 ; S2 |
| US05 | Voir le dépôt traité | `succeeded` ou `failed` ; en-tête invalide → `failed` / `Invalid header` / 0 mesure | F13, F16, F19, F25, I03, I21 ; S2–S4 |
| US06 | Voir les lignes rejetées et leur raison | `mesures-avec-erreurs.csv` : 4 acceptées, 7 rejetées avec raisons ; aucune ligne invalide enregistrée | F14, F17, F18, F28 ; S1–S2 |
| US07 | Redéposer sans doublon | Second dépôt : 0 acceptée, 63 doublons, compteur toujours 63 | F15, I04 ; S2–S3 |
| US08 | Consulter les indicateurs par salle | Moyenne/min/max CO₂, filtres salle et période ; filtre vide → `rooms: []` sans erreur | F23, F24, F28 ; S2 |
| US09 | Relancer un dépôt échoué | `failed` → retraitement ; tout autre statut → 409 | F20–F22, F28 ; S2 |
| US10 | Compter sur un service fiable sans perte de données | Données intactes après redémarrage ; panne DB, reprise, restauration | F26, F27, F29, F31, I05, I06, I09, I10, I11, I13, I16, I17, I18 ; S3–S6 |

Les critères I01, I02, I07, I08, I12, I14, I15, I19 et I20 portent sur la qualité de livraison (Docker, Kubernetes, Cloud, CI) plutôt que sur une US précise.

## 7. Quatre résultats de test attendus (contrat, relevés sur l'implémentation de référence)

1. Fichier de référence `mesures-salles-2026-10-05.csv` dans un jeu vide : `succeeded`, **63 / 0 / 0** ; 63 mesures, `rows_total` 63, `started_at` ≤ `finished_at`, somme de contrôle `sum(co2_ppm)` = **46 504** ; trois salles de 21 mesures, A101 : CO₂ moyen 636.1, min 430, max 1092 ; A102 max 1304 ; B201 max 1572.
2. Second dépôt du même fichier dans le même jeu : `succeeded`, **0 / 0 / 63** ; `measurement_count` toujours 63.
3. `mesures-avec-erreurs.csv` dans un jeu vide : `succeeded`, **4 / 7 / 1** ; `errors` aux lignes 5, 6, 7, 8, 9, 10 et 12 avec les raisons du contrat (la ligne 11 reprend la ligne 3 et compte comme doublon).
4. `en-tete-invalide.csv` : `failed`, `error_message` = **`Invalid header`**, 0 mesure ajoutée.

Compléments contractuels : 30 lignes invalides → `rows_rejected` = 30 et `errors` limité à 20 (F17) ; règle « date future » testée avec `now` injecté (F18) ; deux prises en charge concurrentes → un seul dépôt pris (F19). Identifiants et dates des exemples sont illustratifs, jamais codés en dur. Les deux tests du socle ne valident ni l'API métier ni l'ingestion.

## 8. Méthodologie, Git et sécurité

- Transformer un TODO en réalisation vérifiée : retrouver la règle dans le contrat commun et un exemple positif/négatif → identifier le fichier responsable (pas toute la logique dans `main.py`) → écrire la plus petite opération conforme → ajouter la vérification observable et relire après une mutation refusée → intégrer au composant voisin puis réaliser le parcours utilisateur → remplacer le TODO par un commentaire d'intention si nécessaire → consigner **commit, résultat et limite** dans la recette.
- Commentaires : près de la décision expliquée ; préférer une phrase sur l'invariant à dix lignes d'affectations ; docstring des fonctions importantes (rôle, résultat, erreurs) ; en YAML expliquer les liens entre champs et hypothèses du laboratoire. Aucune valeur secrète dans un commentaire (texte versionné et parfois embarqué dans l'image).
- Questions auxquelles les commentaires doivent répondre : Session par requête et fermeture sur erreur ; pourquoi un même fichier déposé deux fois ne crée pas de doublon ; pourquoi `SKIP LOCKED` ; pourquoi la liveness ne consulte pas PostgreSQL ; pourquoi le volume DB survit au conteneur ; pourquoi un Pod Running peut ne pas être prêt ; pourquoi une CI verte ne déploie pas automatiquement la VM.
- Revue croisée en cinq questions : nom du composant ; règle au bon endroit et test observable ; commentaire encore vrai ; exception laisse transaction, dépôt et boutons cohérents ; une autre personne peut relier décision, contrat et preuve.
- Les fichiers modifiables indiquent **CONTEXTE ÉTUDIANT**, **À PRÉPARER / ADAPTER** ou **À RÉALISER**, puis **CONTRÔLE ATTENDU** : lire ces trois indications avant modification.
- Requirements.lock / requirements-dev.lock sont générés : ne pas les annoter ni modifier des versions au hasard. Documenter les intentions dans les `.in` et le journal, puis régénérer les deux locks ensemble et revérifier installation et tests.
- `.env.example` ne contient que des placeholders. `.env`, dumps, clés et kubeconfigs sont ignorés par Git. Ne jamais publier les valeurs réelles. Aucun secret, dump, certificat privé, kubeconfig ou clé SSH dans le dépôt/archive. En cas de secret réel publié : révoquer/remplacer, corriger le dépôt avant toute nouvelle diffusion, expliquer l'incident sans le masquer.
- Ne pas utiliser `docker compose down -v` ni supprimer un PVC avant d'avoir sauvegardé les données utiles.
- Images : associer la release au commit ; aucun tag `latest` applicatif ; identifier SHA + digests + endpoint version. Distinguer commit, tag, digest, publication et promotion. Un rollback d'image n'annule pas une migration SQL.
- Contrôles à exécuter depuis le projet étudiant : Ruff et pytest réussis (locks cohérents, installation reproductible). Les tests métier utilisent un PostgreSQL dédié isolé (`campus_test`) ; pytest appelle l'API dans le processus.

## 9. Livrables, preuves et exploitation

- Séances : S1 cadrage/conception et socle ; S2 modules métier, interface, tests ; S3 Compose (4 services db, api, worker, web) ; S4 manifestes Kubernetes + CronJob après import des images dans k3d ; S5 publication des images et overlay cloud par digests ; S6 `github-workflows/ci.yaml` → `.github/workflows/ci.yaml` adapté aux tests métier, README final à partir de `documents/readme-livraison.md`.
- Chaque exigence relie **besoin (US et critère) → implémentation (fichier responsable) → test (automatisé ou manuel) → preuve (sortie expurgée, version) → résultat**. Une commande copiée sans résultat n'est pas une preuve ; un écran favorable seul ne valide ni persistance, ni cloud, ni rollback. Une anomalie documentée vaut mieux qu'un succès inventé.
- `documents/recette.md` : pour chaque test, commit, environnement, préconditions, action, résultat attendu, observation et statut **validé / échoué / non exécuté / non applicable avec justification**. Une preuve reste liée à sa version : rejouer les vérifications après modification.
- Traces à conserver par séance : S1 versions, commit et réponses du socle ; S2 tests métier et recette navigateur ; S3 version, UID, volume, jeu témoin avant/après ; S4 états, événements, requêtes et données relues ; S5 digests, contexte cloud, logs, Job et indicateurs par tunnel ; S6 runs, versions, témoin restauré et inventaire final.
- Jeu témoin : 63 mesures, `sum(co2_ppm)` = 46 504 ; prouver identifiant, `measurement_count` et somme avant/après remplacement du processus DB et après restauration d'un dump (commandes, résultat, durée).
- Exigences non fonctionnelles mesurables et preuves : persistance ; idempotence (0 acceptée, 63 doublons) ; traitement < 10 s sous Compose et < 2 min sous Kubernetes (horodatages `created_at`/`finished_at`) ; 2 Pods API prêts puis 1 supprimé et remplacé (`kubectl get pods` + requête) ; 20 lectures séquentielles des indicateurs, médiane < 500 ms hors téléchargement initial, mesurée avec `proofs/latence-<environnement>.json`, matériel/environnement/nombre de mesures/tunnel mentionnés ; panne DB → readiness 503 et liveness 200, worker sans perte de dépôt, retour après rétablissement ; API et worker non root, DB non publiée, aucun secret dans Git (UID, services/ports, revue des fichiers) ; images liées au commit, digests et endpoint version.
- Limites à expliquer à l'oral : disque local ≠ sauvegarde ; un PVC ne garantit pas la réplication ; deux Pods sur un nœud ne protègent pas de sa perte ; une readiness ne valide pas tout le métier ; worker interrompu → dépôt `running` ; fichier brut en base adapté au volume du TP, pas à de gros fichiers (stockage objet en extension) ; rollback d'image ≠ restauration SQL ; CI verte à deux tests superficiels ≠ qualité.
- Vérification finale du dossier : README commençant par besoin et architecture puis commandes ; chemins et noms de services conformes ; poste/conteneur/VM indiqué partout ; locks, Dockerfiles, Compose, manifests et CI présents ; recette distinguant succès, anomalies et non-réalisations ; commit final, release et digests identifiés ; restauration et nettoyage prouvés ; chaque membre a renseigné son journal et comprend le parcours. Le README final doit pouvoir être suivi par une autre équipe.
- Barème sur 100 points : Conception 15 ; Développement et tests 25 ; Docker et Compose 15 ; Kubernetes 15 ; Cloud 10 ; CI et exploitation 15 ; Documentation et soutenance 5. Les extensions n'ajoutent pas de points au-delà de 100.

## 10. Les 10 skills installés dans `.opencode/skills/` et quand les utiliser

| Fichier | Skill | Quand l'utiliser |
|---|---|---|
| `skill_api_designSKILL.md` | `api-design` | Concevoir ou relire des endpoints REST, noms de ressources, codes de statut, filtrage, pagination, gestion d'erreurs, versioning. |
| `skill_docker_patternsSKILL.md` | `docker-patterns` | Créer ou relire des Dockerfiles et services Compose, réseau/volumes, contexte de build, sécurité des conteneurs, utilisateur non root. |
| `skill_fastapi_patternsSKILL.md` | `fastapi-patterns` | Construire ou relire l'API FastAPI : schémas Pydantic, dépendances, couche service transactionnelle, handlers, tests httpx/pytest. |
| `skill_generating_python_installerSKILL.md` | `generating-python-installer` | Uniquement pour un packaging Windows avancé (Nuitka + Inno Setup, taille/démarrage optimisés) ; hors périmètre du socle CampusData. |
| `skill_kubernetes_patternsSKILL.md` | `kubernetes-patterns` | Écrire ou relire les manifestes (Deployments, Services, Ingress, CronJob), probes, ressources, ConfigMap/Secret, RBAC, et déboguer les Pods. |
| `skill_orch_pipelineSKILL.md` | `orch-pipeline` | Moteur indirect des opérations `orch-*` : cadrage, plan, TDD, revue, gates humains ; le lire directement seulement pour ajouter une opération ou régler les phases. |
| `skill_postgres_patternsSKILL.md` | `postgres-patterns` | Concevoir le schéma et les index PostgreSQL, écrire des requêtes, diagnostiquer une requête lente, file d'attente `FOR UPDATE SKIP LOCKED`. |
| `skill_python_patternsSKILL.md` | `python-patterns` | Écrire, relire ou refactoriser du Python idiomatique : lisibilité, typage, PEP 8, structure de modules. |
| `skill_python_testingSKILL.md` | `python-testing` | Écrire ou relire les tests pytest : TDD rouge/vert/refactor, fixtures, parametrization, mocks, couverture. |
| `skill_security_scanSKILL.md` | `security-scan` | Auditer une configuration `.claude/` (CLAUDE.md, settings.json, MCP, hooks, agents) avec AgentShield avant commit ou à l'onboarding. |

Note : `.opencode/skills/SKILL.md` est une copie du skill `security-scan` ; la liste ci-dessus compte les 10 skills distincts. Les recommandations générales de ces skills ne remplacent pas le contrat CampusData.
