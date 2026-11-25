# CONTEXTE ÉTUDIANT : S1-S2 | point d’entrée Uvicorn app.main:app
# À PRÉPARER / ADAPTER : Charger DATABASE_URL avant le lancement. Compléter les TODO selon le contrat.
# CONTRÔLE ATTENDU : Contrôler live/ready/version, puis les routes métier après votre réalisation.
#
"""Point d'entrée du socle CampusData, à compléter pendant la séance 2.

Le starter expose uniquement la santé du processus, l'accès DB et la version.
Il ne contient ni tables (datasets, ingestions, measurements), ni routes
métier, ni lecture CSV, ni worker d'ingestion.
En S2, déplacer la connexion vers database.py et inclure le routeur métier.
Garder une seule source de configuration pour les probes et les services.
"""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Cette version décrit le contrat OpenAPI ; /api/version identifie la release.
app = FastAPI(title="CampusData", version="0.1.0")
# La variable doit exister AVANT l'import du module, y compris sous pytest.
# Son hôte dépend du contexte : poste = 127.0.0.1 ; Compose/Kubernetes = db.
# L'engine gère le pool de connexions. Ce n'est pas une Session de transaction.
engine = create_engine(
    os.environ["DATABASE_URL"],
    # Vérifier les connexions sorties du pool aide après une coupure DB.
    # Cela ne rejoue pas automatiquement une transaction interrompue.
    pool_pre_ping=True,
    # Borner l'établissement de connexion ; ce n'est pas un délai global SQL.
    connect_args={"connect_timeout": 3},
)


@app.get("/health/live")
def live():
    """Vérifier le processus sans dépendre de la disponibilité de PostgreSQL."""
    # Une panne DB doit modifier la readiness, pas provoquer une boucle
    # de redémarrages d'un processus API qui fonctionne encore.
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    """Vérifier la connexion DB ; ajouter le contrôle de table en séance 2."""
    try:
        # Le contexte libère la connexion même lorsqu'une exception remonte.
        with engine.connect() as connection:
            # SELECT 1 prouve une connexion, pas l'existence du schéma métier.
            # TODO S2 : lire aussi datasets, ingestions et measurements
            # (SELECT 1 FROM <table> LIMIT 1). Une table vide reste valide.
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Réponse publique générique : ne jamais renvoyer le DSN ou le secret.
        # Cette interception est limitée à la probe. Dans les routes métier, distinguer
        # indisponibilité DB, conflit métier et erreur de programmation.
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ready"}


@app.get("/api/version")
def version():
    """Lire la référence écrite au build, ou dev lors d'une exécution locale."""
    # Le chemin est relatif au module, pas au dossier courant du terminal.
    version_file = Path(__file__).with_name("VERSION")
    value = version_file.read_text().strip() if version_file.exists() else "dev"
    # La version permet une vérification croisée avec le commit et le digest.
    # Ce champ seul ne prouve pas que toute la recette a été exécutée.
    return {"version": value}

# TODO S2 : models.py, schemas.py, database.py, services.py, routes.py.
# TODO S2 : ingestion.py (lecture et contrôle du CSV) et worker.py (traitement
#           des dépôts pending, hors du processus API).
# TODO S2 : une Session par requête ; fermeture et rollback sur échec.
# TODO S2 : initialisation explicite dans app/init_db.py, hors démarrage API.
# TODO S2 : inclure les routeurs /api/datasets et /api/ingestions.
