# CONTEXTE ÉTUDIANT : S2 | fixtures pytest sur PostgreSQL campus_test
# À PRÉPARER / ADAPTER : exporter DATABASE_URL avant de lancer pytest.
# CONTRÔLE ATTENDU : refus d'une base non _test, tables vides avant chaque test.
#
"""Fixtures partagées par les tests métier CampusData.

La garde sur le nom de base est volontairement au chargement de conftest :
pytest ne doit jamais tronquer campus. Les tests appellent l'API
dans le processus avec TestClient, sans Uvicorn ni serveur TCP.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_NAME = make_url(DATABASE_URL).database or ""
if not DB_NAME.endswith("_test"):
    raise RuntimeError(
        "Les tests doivent utiliser une base *_test ; DATABASE_URL pointe vers "
        f"{DB_NAME or '<absente>'}"
    )

from app import worker  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

# Instant injecté dans le worker : les fichiers du kit restent dans le passé
# et la ligne volontairement datée de 2030 reste rejetée pour toujours.
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


class _FrozenDatetime:
    """Remplace datetime.now() du worker par NOW pendant les tests."""

    @staticmethod
    def now(tz=None):
        return NOW


@pytest.fixture(autouse=True)
def clean_db():
    """Vider les trois tables avant chaque test, sans toucher à campus."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE measurements, ingestions, datasets RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture
def client():
    """Client HTTP en processus, avec la même DB que les services."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session():
    """Session SQLAlchemy dédiée aux vérifications de persistance."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def data_file():
    """Lire les CSV du kit sans dépendre du répertoire courant."""
    root = Path(__file__).resolve().parents[2]

    def _read(name: str) -> bytes:
        return (root / "data" / name).read_bytes()

    return _read


@pytest.fixture
def dataset(client):
    """Créer un jeu témoin et renvoyer sa représentation JSON."""
    response = client.post(
        "/api/datasets",
        json={"name": "Qualité de l'air - bâtiment A", "owner": "Équipe A"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def upload(client, data_file):
    """Déposer un fichier de data/ sur un jeu, avec le bon Content-Type."""

    def _upload(
        dataset_id,
        name: str,
        *,
        filename: str | None = None,
        content: bytes | None = None,
        content_type: str = "text/csv",
    ):
        return client.post(
            f"/api/datasets/{dataset_id}/ingestions",
            params={"filename": filename or name},
            content=content if content is not None else data_file(name),
            headers={"Content-Type": content_type},
        )

    return _upload


@pytest.fixture
def process_pending(monkeypatch):
    """Lancer claim_next + process sur tous les dépôts en attente."""
    monkeypatch.setattr(worker, "datetime", _FrozenDatetime)

    def _run():
        outcomes = []
        while True:
            db = SessionLocal()
            try:
                ingestion = worker.claim_next(db)
                if ingestion is None:
                    break
                outcomes.append((ingestion.id, worker.process(db, ingestion)))
            finally:
                db.close()
        return outcomes

    return _run
