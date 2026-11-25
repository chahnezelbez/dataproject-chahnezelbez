# CONTEXTE ÉTUDIANT : S2 | formes JSON et validation des entrées
# À PRÉPARER / ADAPTER : garder les règles alignées sur SPEC_PROJET.md §3, §4 et §5.
# CONTRÔLE ATTENDU : F01-F05, F10, F20-F24 ; moyennes à 1 décimale, rooms: [].
#
"""Schémas Pydantic de CampusData.

DatasetCreate valide le corps JSON ; DatasetRead et IngestionRead décrivent
les réponses. Les objets SQLAlchemy sont lus avec from_attributes=True.
Pydantic v2 sérialise les datetime aware UTC en ``...Z``, comme attendu par
le contrat pour les TIMESTAMPTZ.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetCreate(BaseModel):
    """Corps accepté par POST /api/datasets."""

    # id, created_at et measurement_count sont générés côté serveur :
    # les refuser comme champs inconnus donne bien 422 (F04).
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=120)

    # Le contrat accepte "" telle quelle ; c'est l'interface qui envoie null.
    # Pas de strip ici : on ne fusionne pas deux représentations de "absent".
    description: str | None = Field(default=None, max_length=2000)

    owner: str = Field(default="Équipe", min_length=2, max_length=60)

    @field_validator("name", "owner", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        # Normaliser AVANT les contraintes de longueur : "  ab  " doit être
        # refusé après strip, pas accepté parce que la chaîne brute fait 6.
        return value.strip() if isinstance(value, str) else value


class DatasetRead(BaseModel):
    """Réponse GET/POST d'un jeu."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    owner: str
    created_at: datetime
    # Champ calculé en SQL par le service : il n'existe pas dans la table.
    measurement_count: int


class IngestionRead(BaseModel):
    """Réponse d'un dépôt : tous les champs sauf le BYTEA content."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    filename: str
    # Même liste que le CHECK SQL de models.py : status est toujours connu.
    status: Literal["pending", "running", "succeeded", "failed"]

    # Compteurs null jusqu'au passage du worker.
    rows_total: int | None
    rows_accepted: int | None
    rows_rejected: int | None
    rows_duplicate: int | None

    # Au plus 20 objets {"line": n, "reason": "..."} ; le CHECK DB porte la limite.
    errors: list[dict[str, object]]
    error_message: str | None

    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RoomStats(BaseModel):
    """Une ligne du tableau d'indicateurs décrit en §4."""

    model_config = ConfigDict(from_attributes=True)

    room: str
    measurements: int
    # func.round(..., 1) est calculé en SQL ; float garde un nombre JSON.
    co2_avg: float
    co2_min: int
    co2_max: int
    temperature_avg: float
    humidity_avg: float
    last_measured_at: datetime


class StatsRead(BaseModel):
    """Réponse GET /api/datasets/{id}/stats, avec filtres renvoyés à l'appelant."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    dataset_id: UUID
    room: str | None = None
    # "from" est un mot réservé en Python : alias JSON et champ interne from_.
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    rooms: list[RoomStats]
