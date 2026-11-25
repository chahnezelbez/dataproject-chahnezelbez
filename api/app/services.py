# CONTEXTE ÉTUDIANT : S2 | cas d'utilisation jeux, dépôts et indicateurs
# À PRÉPARER / ADAPTER : garder les exceptions métier traduisibles par routes.py.
# CONTRÔLE ATTENDU : F01-F12, F20-F24 ; stats en SQL, retry borné à failed.
#
"""Services métier de CampusData.

La Session est reçue de la route (dépendance get_session) : ce module ne
crée ni ne partage de session. Il commit après les écritures et laisse
get_session faire le rollback si une exception remonte. Aucune HTTPException
ici : les routes traduisent les exceptions métier en codes HTTP.
"""
from __future__ import annotations

from datetime import datetime
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


class IngestionNotFound(Exception):
    """Le dépôt demandé n'existe pas."""


class IngestionCannotBeRetried(Exception):
    """Le dépôt n'est pas en failed : la relance est refusée."""


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


def list_ingestions(
    session: Session, dataset_id: UUID, status: str | None = None
) -> list[Ingestion]:
    """Lister les dépôts d'un jeu du plus récent au plus ancien."""
    if session.get(Dataset, dataset_id) is None:
        raise DatasetNotFound(f"Dataset not found: {dataset_id}")

    stmt = select(Ingestion).where(Ingestion.dataset_id == dataset_id)
    if status is not None:
        # La validation de la valeur est faite par la route (422 avant 404).
        stmt = stmt.where(Ingestion.status == status)
    stmt = stmt.order_by(Ingestion.created_at.desc(), Ingestion.id.desc())
    return list(session.scalars(stmt).all())


def get_ingestion(session: Session, ingestion_id: UUID) -> Ingestion:
    """Charger un dépôt ou lever IngestionNotFound."""
    ingestion = session.get(Ingestion, ingestion_id)
    if ingestion is None:
        raise IngestionNotFound("Ingestion not found")
    return ingestion


def retry_ingestion(session: Session, ingestion_id: UUID) -> Ingestion:
    """Relancer un dépôt failed ; toute relance réinitialise ses compteurs."""
    ingestion = session.scalar(
        select(Ingestion)
        .where(Ingestion.id == ingestion_id)
        .with_for_update()
    )
    if ingestion is None:
        raise IngestionNotFound("Ingestion not found")
    if ingestion.status != "failed":
        raise IngestionCannotBeRetried("Ingestion cannot be retried")

    # Le contenu BYTEA reste intact : c'est lui que le worker relira.
    ingestion.status = "pending"
    ingestion.rows_total = None
    ingestion.rows_accepted = None
    ingestion.rows_rejected = None
    ingestion.rows_duplicate = None
    ingestion.error_message = None
    ingestion.started_at = None
    ingestion.finished_at = None
    ingestion.errors = []
    session.commit()
    session.refresh(ingestion)
    return ingestion


def dataset_stats(
    session: Session,
    dataset_id: UUID,
    room: str | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
) -> dict:
    """Agréger les mesures par salle en SQL ; jamais de chargement Python."""
    # §5 impose la validation des paramètres (422) avant la recherche (404).
    if from_ is not None and to is not None and from_ >= to:
        raise ValueError("Invalid period")
    if session.get(Dataset, dataset_id) is None:
        raise DatasetNotFound(f"Dataset not found: {dataset_id}")

    aggregates = (
        Measurement.room.label("room"),
        func.count(Measurement.id).label("measurements"),
        func.round(func.avg(Measurement.co2_ppm), 1).label("co2_avg"),
        func.min(Measurement.co2_ppm).label("co2_min"),
        func.max(Measurement.co2_ppm).label("co2_max"),
        func.round(func.avg(Measurement.temperature_c), 1).label("temperature_avg"),
        func.round(func.avg(Measurement.humidity_pct), 1).label("humidity_avg"),
        func.max(Measurement.measured_at).label("last_measured_at"),
    )
    stmt = select(*aggregates).where(Measurement.dataset_id == dataset_id)
    if room is not None:
        stmt = stmt.where(Measurement.room == room)
    if from_ is not None:
        stmt = stmt.where(Measurement.measured_at >= from_)
    if to is not None:
        # Borne haute exclusive : une mesure à exactement "to" est exclue.
        stmt = stmt.where(Measurement.measured_at < to)
    stmt = stmt.group_by(Measurement.room).order_by(Measurement.room)

    rooms: list[dict[str, object]] = []
    for row in session.execute(stmt).all():
        rooms.append(
            {
                "room": row.room,
                "measurements": row.measurements,
                # round() reste en SQL ; float() ne fait que sérialiser Decimal.
                "co2_avg": float(row.co2_avg),
                "co2_min": row.co2_min,
                "co2_max": row.co2_max,
                "temperature_avg": float(row.temperature_avg),
                "humidity_avg": float(row.humidity_avg),
                "last_measured_at": row.last_measured_at,
            }
        )

    return {
        "dataset_id": dataset_id,
        "room": room,
        "from": from_,
        "to": to,
        "rooms": rooms,
    }
