# CONTEXTE ÉTUDIANT : S2 | cas d'utilisation jeux et dépôts
# À PRÉPARER / ADAPTER : ne pas ajouter les fonctions Tâche 5 ici pour l'instant.
# CONTRÔLE ATTENDU : F01-F12 hors worker ; conflit de nom en 409, jeu absent en 404.
#
"""Services métier de CampusData.

La Session est reçue de la route (dépendance get_session) : ce module ne
crée ni ne partage de session. Il commit après les écritures et laisse
get_session faire le rollback si une exception remonte. Aucune HTTPException
ici : les routes traduisent les exceptions métier en codes HTTP.
"""
from __future__ import annotations

from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Dataset, Ingestion, Measurement
from .schemas import DatasetCreate

DATASET_NAME_UNIQUE = "datasets_name_key"


class DatasetNotFound(Exception):
    """Le jeu demandé n'existe pas."""


class DatasetNameAlreadyExists(Exception):
    """Le nom est déjà utilisé par un autre jeu."""


def _is_dataset_name_conflict(exc: IntegrityError) -> bool:
    """Distinguer le conflit sur datasets.name des autres IntegrityError."""
    original = exc.orig
    return (
        isinstance(original, UniqueViolation)
        and original.diag.table_name == "datasets"
        and original.diag.constraint_name == DATASET_NAME_UNIQUE
    )


def create_dataset(session: Session, payload: DatasetCreate) -> Dataset:
    """Créer un jeu ; un nom déjà pris lève DatasetNameAlreadyExists."""
    dataset = Dataset(
        name=payload.name,
        description=payload.description,
        owner=payload.owner,
    )
    session.add(dataset)
    try:
        session.commit()
    except IntegrityError as exc:
        if not _is_dataset_name_conflict(exc):
            raise
        # Pas de rollback ici : get_session le fera quand l'exception remontera.
        raise DatasetNameAlreadyExists("Dataset name already exists") from None
    # created_at vient du serveur : refresh le charge avec l'id généré.
    session.refresh(dataset)
    dataset.measurement_count = 0
    return dataset


def list_datasets(session: Session) -> list[Dataset]:
    """Lister les jeux du plus récent au plus ancien, avec leur compteur."""
    # Sous-requête corrélée : un seul COUNT par ligne en SQL, pas de N+1 Python.
    count_query = (
        select(func.count(Measurement.id))
        .where(Measurement.dataset_id == Dataset.id)
        .scalar_subquery()
        .label("measurement_count")
    )
    rows = session.execute(
        select(Dataset, count_query).order_by(
            Dataset.created_at.desc(), Dataset.id.desc()
        )
    ).all()

    datasets: list[Dataset] = []
    for dataset, count in rows:
        # measurement_count est calculé : on l'attache à l'instance pour DatasetRead.
        dataset.measurement_count = count or 0
        datasets.append(dataset)
    return datasets


def get_dataset(session: Session, dataset_id: UUID) -> Dataset:
    """Charger un jeu ou lever DatasetNotFound ; joindre son compteur."""
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise DatasetNotFound(f"Dataset not found: {dataset_id}")

    dataset.measurement_count = (
        session.scalar(
            select(func.count(Measurement.id)).where(
                Measurement.dataset_id == dataset_id
            )
        )
        or 0
    )
    return dataset


def delete_dataset(session: Session, dataset_id: UUID) -> None:
    """Supprimer un jeu ; la cascade DB emporte dépôts et mesures."""
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise DatasetNotFound(f"Dataset not found: {dataset_id}")
    # passive_deletes=True sur les relations : SQLAlchemy ne charge pas les
    # enfants, PostgreSQL applique ON DELETE CASCADE.
    session.delete(dataset)
    session.commit()


def create_ingestion(
    session: Session, dataset_id: UUID, filename: str, content: bytes
) -> Ingestion:
    """Enregistrer un dépôt pending avec ses octets bruts, sans traiter le CSV."""
    if session.get(Dataset, dataset_id) is None:
        raise DatasetNotFound(f"Dataset not found: {dataset_id}")

    ingestion = Ingestion(
        dataset_id=dataset_id,
        filename=filename,
        status="pending",
        content=content,
        errors=[],
        error_message=None,
    )
    # Les compteurs rows_* restent None jusqu'au passage du worker.
    session.add(ingestion)
    session.commit()
    session.refresh(ingestion)
    return ingestion
