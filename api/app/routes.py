# CONTEXTE ÉTUDIANT : S2 | routes HTTP des jeux et dépôts
# À PRÉPARER / ADAPTER : ne pas ajouter stats/liste dépôts/retry (Tâche 5).
# CONTRÔLE ATTENDU : F01-F12 ; 415 → 413 → 422 → 404 dans l'ordre du contrat.
#
"""Couche HTTP de CampusData.

Les routes valident la requête, appellent services.py et choisissent le code
de réponse. Aucun SQL ici, aucune lecture CSV : le corps n'est que stocké.
Les erreurs métier deviennent des HTTPException avec les messages exacts.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from . import services
from .database import get_session
from .models import Dataset, Ingestion
from .schemas import DatasetCreate, DatasetRead, IngestionRead

MAX_UPLOAD_BYTES = 1_048_576
CSV_CONTENT_TYPE = "text/csv"
FILENAME_PATTERN = r"^[^/\\]+$"


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

    # La ressource pointée sera exposée en Tâche 5 ; le lien est déjà valide.
    response.headers["Location"] = f"/api/ingestions/{ingestion.id}"
    return ingestion
