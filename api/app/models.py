# CONTEXTE ÉTUDIANT : S2 | schéma PostgreSQL des trois tables métier
# À PRÉPARER / ADAPTER : garder les contraintes SQL alignées sur le contrat et les schémas Pydantic.
# CONTRÔLE ATTENDU : création idempotente du schéma, second dépôt sans doublon, valeurs hors bornes refusées.
#
"""Déclarations SQLAlchemy de CampusData.

Ce module ne contient ni session ni connexion : il définit uniquement les tables
que app.init_db créera explicitement avant l'ouverture du trafic. Les contraintes
SQL protègent les écritures qui contournent l'API ; les contrôles du worker
produisent le rapport lisible attendu par l'utilisateur.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base déclarative commune, source unique de ``Base.metadata.create_all``."""


class Dataset(Base):
    """Jeu de données regroupant ses dépôts et ses mesures."""

    __tablename__ = "datasets"

    # Identifiant généré côté serveur : le client ne choisit jamais la clé.
    # gen_random_uuid() est disponible dans PostgreSQL 13+ sans extension.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(String(60), nullable=False, default="Équipe")
    # TIMESTAMPTZ et aucune valeur de mise à jour : created_at est immuable.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ingestions: Mapped[list[Ingestion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )
    measurements: Mapped[list[Measurement]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(name)) >= 3", name="ck_datasets_name_min_length"
        ),
        CheckConstraint(
            "char_length(btrim(owner)) >= 2", name="ck_datasets_owner_min_length"
        ),
        CheckConstraint(
            "char_length(description) <= 2000", name="ck_datasets_description_max_length"
        ),
    )


class Ingestion(Base):
    """Dépôt CSV : les octets bruts restent en base pour permettre une relance."""

    __tablename__ = "ingestions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    # BYTEA et non TEXT : un fichier non UTF-8 doit être stocké pour être refusé
    # par le worker avec un rapport explicite. Ce champ n'est jamais sérialisé
    # dans IngestionRead.
    content: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_accepted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_rejected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_duplicate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    dataset: Mapped[Dataset] = relationship(back_populates="ingestions")
    measurements: Mapped[list[Measurement]] = relationship(
        back_populates="ingestion", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_ingestions_status",
        ),
        # chr(92) est le backslash : éviter l'ambiguïté d'échappement de LIKE.
        CheckConstraint(
            "char_length(filename) BETWEEN 1 AND 255 "
            "AND strpos(filename, '/') = 0 AND strpos(filename, chr(92)) = 0",
            name="ck_ingestions_filename",
        ),
        CheckConstraint(
            "octet_length(content) <= 1048576", name="ck_ingestions_content_max_size"
        ),
        CheckConstraint("jsonb_array_length(errors) <= 20", name="ck_ingestions_errors_max"),
        CheckConstraint(
            "rows_total >= 0 AND rows_accepted >= 0 "
            "AND rows_rejected >= 0 AND rows_duplicate >= 0",
            name="ck_ingestions_counters_non_negative",
        ),
        # Un dépôt réussi doit se décomposer exactement ; les compteurs NULL
        # sont exclus explicitement car un CHECK les considérerait comme vrai.
        CheckConstraint(
            "status <> 'succeeded' OR ("
            "rows_total IS NOT NULL AND rows_accepted IS NOT NULL "
            "AND rows_rejected IS NOT NULL AND rows_duplicate IS NOT NULL "
            "AND rows_total = rows_accepted + rows_rejected + rows_duplicate)",
            name="ck_ingestions_succeeded_totals",
        ),
        # Le worker filtre sur status puis trie par created_at : index composite
        # dans cet ordre. Coût : chaque insertion et chaque changement de statut
        # met aussi à jour cet index, acceptable à ce volume pédagogique.
        Index("ix_ingestions_status_created_at", "status", "created_at"),
    )


class Measurement(Base):
    """Mesure d'une salle ; l'identifiant BIGINT est technique et non exposé."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ingestions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room: Mapped[str] = mapped_column(String(30), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    co2_ppm: Mapped[int] = mapped_column(Integer, nullable=False)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    humidity_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="measurements")
    ingestion: Mapped[Ingestion] = relationship(back_populates="measurements")

    __table_args__ = (
        # C'est cette unicité, avec ON CONFLICT DO NOTHING du worker, qui rend
        # un second dépôt du même fichier idempotent. Elle sert aussi d'index
        # (préfixe dataset_id) aux agrégations par salle.
        UniqueConstraint(
            "dataset_id",
            "room",
            "measured_at",
            name="uq_measurements_dataset_room_measured_at",
        ),
        CheckConstraint(
            "char_length(btrim(room)) >= 1", name="ck_measurements_room_min_length"
        ),
        CheckConstraint(
            "co2_ppm BETWEEN 250 AND 10000", name="ck_measurements_co2_ppm"
        ),
        CheckConstraint(
            "temperature_c BETWEEN -30 AND 60", name="ck_measurements_temperature_c"
        ),
        CheckConstraint(
            "humidity_pct BETWEEN 0 AND 100", name="ck_measurements_humidity_pct"
        ),
    )
