# CONTEXTE ÉTUDIANT : S1-S2 | point d’entrée Uvicorn app.main:app
# À PRÉPARER / ADAPTER : garder une seule source DB (database.py) et inclure routes.py quand il existe.
# CONTRÔLE ATTENDU : live 200 sans DB, ready 200 seulement si les 3 tables existent, version inchangée.
#
"""Point d'entrée de l'API CampusData.

L'engine et les sessions sont centralisés dans database.py : ce module ne crée
plus de create_engine local. Les probes peuvent être testés avant la Tâche 3 :
l'absence de routes.py est tolérée, mais pas une erreur dans ses dépendances.
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import engine

logger = logging.getLogger(__name__)

# Cette version décrit le contrat OpenAPI ; /api/version identifie la release.
app = FastAPI(title="CampusData", version="0.1.0")

# La variable DATABASE_URL doit exister AVANT l'import du module, y compris sous pytest.
# Son hôte dépend du contexte : poste = 127.0.0.1 ; Compose/Kubernetes = db.
# Les choix pool_pre_ping et connect_timeout sont expliqués dans database.py.

try:
    from .routes import router
except ModuleNotFoundError as exc:
    # Tâche 3 pas encore faite : seul le module app.routes peut manquer.
    # Une dépendance interne (app.services, par exemple) doit au contraire
    # faire échouer le démarrage, sinon on masquerait une vraie erreur.
    if exc.name != "app.routes":
        raise
    logger.warning(
        "app.routes absent : seules les probes sont disponibles pour l'instant"
    )
    router = None

if router is not None:
    app.include_router(router)


@app.get("/health/live")
def live():
    """Vérifier le processus sans dépendre de la disponibilité de PostgreSQL."""
    # Une panne DB doit modifier la readiness, pas provoquer une boucle
    # de redémarrages d'un processus API qui fonctionne encore.
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    """Vérifier la connexion DB et l'existence des trois tables métier."""
    try:
        # Le contexte libère la connexion même lorsqu'une exception remonte.
        with engine.connect() as connection:
            # SELECT 1 prouve la connexion ET l'existence de la table.
            # Une table vide reste valide : on ne compte pas ses lignes.
            # Les trois noms sont littéraux : aucune injection possible ici.
            connection.execute(text("SELECT 1 FROM datasets LIMIT 1"))
            connection.execute(text("SELECT 1 FROM ingestions LIMIT 1"))
            connection.execute(text("SELECT 1 FROM measurements LIMIT 1"))
    except SQLAlchemyError:
        # Réponse publique générique : ne jamais renvoyer le DSN ou le secret.
        # Ici, une table absente est aussi une DB indisponible pour l'API.
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
