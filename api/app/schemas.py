# CONTEXTE ÉTUDIANT : S2 | formes JSON et validation des entrées
# À PRÉPARER / ADAPTER : garder les règles alignées sur SPEC_PROJET.md §3, §5 et le tableau de nullité.
# CONTRÔLE ATTENDU : F01-F05 (création de jeu) et F10 (réponse de dépôt sans content).
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
