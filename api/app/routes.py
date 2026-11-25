# CONTEXTE ÉTUDIANT : S2 | routes HTTP des jeux, dépôts et indicateurs
# À PRÉPARER / ADAPTER : traduire les exceptions métier en codes du §5.
# CONTRÔLE ATTENDU : F01-F24 ; 415 → 413 → 422 → 404 ; période invalide en 422.
#
"""Couche HTTP de CampusData.

Les routes valident la requête, appellent services.py et choisissent le code
de réponse. Aucun SQL ici, aucune lecture CSV : le corps n'est que stocké.
Les erreurs métier deviennent des HTTPException avec les messages exacts.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from . import services
from .database import get_session
from .models import Dataset, Ingestion
from .schemas import DatasetCreate, DatasetRead, IngestionRead, StatsRead

MAX_UPLOAD_BYTES = 1_048_576
CSV_CONTENT_TYPE = "text/csv"
FILENAME_PATTERN = r"^[^/\\]+$"
IngestionStatus = Literal["pending", "running", "succeeded", "failed"]


async def raw_body(request: Request) -> bytes:
    """Lire le corps brut sans laisser FastAPI répondre 422 à la place."""
    # Seul ce dependency est async : il n'y a ici ni SQL ni lecture CSV.
    return await request.body()


def _filename_validation_error(
    error_type: str,
    message: str,
    value: str | None,
    ctx: dict[str, object] | None = None,
) -> HTTPException:
    """Fabriquer un 422 avec detail liste, comme la validation FastAPI."""
    error: dict[str, object] = {
        "type": error_type,
        "loc": ["query", "filename"],
        "msg": message,
        "input": value,
    }
    if ctx is not None:
        error["ctx"] = ctx
    return HTTPException(status_code=422, detail=[error])


def _naive_datetime_error(name: str, value: datetime) -> HTTPException:
    """422 liste pour un filtre de date sans fuseau, comme §4 l'exige."""
    return HTTPException(
        status_code=422,
        detail=[
            {
                "type": "datetime_parsing",
                "loc": ["query", name],
                "msg": "Input should be an ISO 8601 datetime with a timezone",
                "input": value.isoformat(),
            }
        ],
    )


router = APIRouter(prefix="/api")


@router.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(
    payload: DatasetCreate, session: Session = Depends(get_session)
) -> Dataset:
    """Créer un jeu : 201, ou 409 si le nom est déjà pris."""
    try:
        return services.create_dataset(session, payload)
    except services.DatasetNameAlreadyExists:
        raise HTTPException(
            status_code=409, detail="Dataset name already exists"
        ) from None


@router.get("/datasets", response_model=list[DatasetRead])
def list_datasets(session: Session = Depends(get_session)) -> list[Dataset]:
    """Lister les jeux ; le tri est appliqué dans le service."""
    return services.list_datasets(session)


@router.get("/datasets/{dataset_id}", response_model=DatasetRead)
def get_dataset(
    dataset_id: UUID, session: Session = Depends(get_session)
) -> Dataset:
    """Lire un jeu : 404 si l'UUID n'existe pas."""
    try:
        return services.get_dataset(session, dataset_id)
    except services.DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found") from None


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: UUID, session: Session = Depends(get_session)
) -> None:
    """Supprimer un jeu : 204 sans corps, 404 si absent."""
    try:
        services.delete_dataset(session, dataset_id)
    except services.DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found") from None


@router.post(
    "/datasets/{dataset_id}/ingestions",
    response_model=IngestionRead,
    status_code=202,
)
def create_ingestion(
    dataset_id: UUID,
    request: Request,
    response: Response,
    # Sans min_length ni pattern : FastAPI ne doit pas répondre 422 avant
    # les contrôles 415/413/422 « Empty file » ci-dessous.
    filename: str | None = Query(None),
    raw_body: bytes = Depends(raw_body),
    session: Session = Depends(get_session),
) -> Ingestion:
    """Enregistrer un dépôt pending et renvoyer son Location."""
    # Ordre imposé par le contrat : type, taille, vide, filename, puis 404.
    content_type = request.headers.get("content-type")
    if content_type != CSV_CONTENT_TYPE:
        raise HTTPException(status_code=415, detail="Expected text/csv")
    if len(raw_body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    if not raw_body:
        raise HTTPException(status_code=422, detail="Empty file")

    if filename is None:
        raise _filename_validation_error("missing", "Field required", None)
    if len(filename) < 1:
        raise _filename_validation_error(
            "string_too_short",
            "String should have at least 1 character",
            filename,
            {"min_length": 1},
        )
    if len(filename) > 255:
        raise _filename_validation_error(
            "string_too_long",
            "String should have at most 255 characters",
            filename,
            {"max_length": 255},
        )
    if "/" in filename or "\\" in filename:
        raise _filename_validation_error(
            "string_pattern_mismatch",
            f"String should match pattern '{FILENAME_PATTERN}'",
            filename,
            {"pattern": FILENAME_PATTERN},
        )

    try:
        ingestion = services.create_ingestion(
            session, dataset_id, filename, raw_body
        )
    except services.DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found") from None

    # GET /api/ingestions/{id} existe désormais : le Location est suivable.
    response.headers["Location"] = f"/api/ingestions/{ingestion.id}"
    return ingestion


@router.get("/datasets/{dataset_id}/ingestions", response_model=list[IngestionRead])
def list_dataset_ingestions(
    dataset_id: UUID,
    # Literal : un statut inconnu est un 422 FastAPI avant le 404 du service.
    status: IngestionStatus | None = Query(None),
    session: Session = Depends(get_session),
) -> list[Ingestion]:
    """Lister les dépôts d'un jeu, du plus récent au plus ancien."""
    try:
        return services.list_ingestions(session, dataset_id, status)
    except services.DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found") from None


@router.get("/ingestions/{ingestion_id}", response_model=IngestionRead)
def get_ingestion(
    ingestion_id: UUID, session: Session = Depends(get_session)
) -> Ingestion:
    """Lire un dépôt : 404 si l'UUID n'existe pas."""
    try:
        return services.get_ingestion(session, ingestion_id)
    except services.IngestionNotFound:
        raise HTTPException(status_code=404, detail="Ingestion not found") from None


@router.post("/ingestions/{ingestion_id}/retry", response_model=IngestionRead)
def retry_ingestion(
    ingestion_id: UUID, session: Session = Depends(get_session)
) -> Ingestion:
    """Relancer un dépôt failed : 404 si absent, 409 pour tout autre statut."""
    try:
        return services.retry_ingestion(session, ingestion_id)
    except services.IngestionNotFound:
        raise HTTPException(status_code=404, detail="Ingestion not found") from None
    except services.IngestionCannotBeRetried:
        raise HTTPException(
            status_code=409, detail="Ingestion cannot be retried"
        ) from None


@router.get("/datasets/{dataset_id}/stats", response_model=StatsRead)
def dataset_stats(
    dataset_id: UUID,
    room: str | None = Query(None),
    # "from" est réservé en Python : alias query + champ interne from_.
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    session: Session = Depends(get_session),
) -> dict:
    """Indicateurs par salle : from inclusif, to exclusif, période validée."""
    if from_ is not None and (from_.tzinfo is None or from_.utcoffset() is None):
        raise _naive_datetime_error("from", from_)
    if to is not None and (to.tzinfo is None or to.utcoffset() is None):
        raise _naive_datetime_error("to", to)
    try:
        return services.dataset_stats(session, dataset_id, room, from_, to)
    except services.DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found") from None
    except ValueError as exc:
        if str(exc) != "Invalid period":
            raise
        raise HTTPException(status_code=422, detail="Invalid period") from None
