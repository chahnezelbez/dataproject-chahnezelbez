# CONTEXTE ÉTUDIANT : S2 | worker PostgreSQL, hors processus API
# À PRÉPARER / ADAPTER : boucle, --once et reprise après panne DB.
# CONTRÔLE ATTENDU : 63/0/0 puis 0/0/63, failed sur en-tête invalide, SKIP LOCKED.
#
"""Worker de traitement des dépôts CSV.

Le worker n'expose aucun port : il interroge PostgreSQL avec SessionLocal,
appelle le module pur ingestion.py, puis conclut le dépôt. Trois transactions
distinctes : prise en charge, traitement, et enregistrement d'un éventuel échec.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal
from .ingestion import parse_csv
from .models import Ingestion, Measurement

logger = logging.getLogger(__name__)
WORKER_INTERVAL_SECONDS = 5


def _interval_seconds() -> int:
    """Lire l'intervalle sans faire échouer le worker sur une valeur invalide."""
    raw = os.getenv("WORKER_INTERVAL_SECONDS", str(WORKER_INTERVAL_SECONDS))
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning(
            "Invalid WORKER_INTERVAL_SECONDS=%r, using %s", raw, WORKER_INTERVAL_SECONDS
        )
        return WORKER_INTERVAL_SECONDS


def claim_next(session: Session) -> Ingestion | None:
    """Prendre un dépôt pending, le passer en running et COMMIT en transaction 1."""
    stmt = (
        select(Ingestion)
        .where(Ingestion.status == "pending")
        .order_by(Ingestion.created_at, Ingestion.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    ingestion = session.scalars(stmt).first()
    if ingestion is None:
        return None

    ingestion_id = ingestion.id
    filename = ingestion.filename
    ingestion.status = "running"
    ingestion.started_at = datetime.now(timezone.utc)
    session.commit()
    # SKIP LOCKED : deux workers concurrents sautent la ligne déjà verrouillée
    # par l'autre, donc aucun dépôt n'est traité deux fois.
    logger.info("Claimed ingestion %s (%s)", ingestion_id, filename)
    return ingestion


def _existing_keys(session: Session, dataset_id: UUID) -> set[tuple[str, datetime]]:
    """Clés déjà présentes dans le jeu, pour détecter les doublons avant INSERT."""
    rows = session.execute(
        select(Measurement.room, Measurement.measured_at).where(
            Measurement.dataset_id == dataset_id
        )
    ).all()
    return {(room, measured_at) for room, measured_at in rows}


def _mark_failed(session: Session, ingestion_id: UUID, message: str) -> None:
    """Transaction 3 : enregistrer l'échec après ROLLBACK de la transaction 2."""
    ingestion = session.get(Ingestion, ingestion_id)
    if ingestion is None:
        logger.error("Ingestion %s vanished before failure could be stored", ingestion_id)
        return
    ingestion.status = "failed"
    ingestion.error_message = message
    ingestion.finished_at = datetime.now(timezone.utc)
    ingestion.errors = []
    ingestion.rows_total = None
    ingestion.rows_accepted = None
    ingestion.rows_rejected = None
    ingestion.rows_duplicate = None
    session.commit()


def process(session: Session, ingestion: Ingestion) -> bool:
    """Traiter un dépôt : True si succeeded, False si failed."""
    ingestion_id = ingestion.id
    dataset_id = ingestion.dataset_id
    try:
        report = parse_csv(
            bytes(ingestion.content),
            datetime.now(timezone.utc),
            _existing_keys(session, dataset_id),
        )

        params = [
            {
                "dataset_id": dataset_id,
                "ingestion_id": ingestion_id,
                "room": row.room,
                "measured_at": row.measured_at,
                "co2_ppm": row.co2_ppm,
                "temperature_c": row.temperature_c,
                "humidity_pct": row.humidity_pct,
            }
            for row in report.rows
        ]
        if params:
            # La UNIQUE (dataset_id, room, measured_at) est la protection finale
            # si une autre écriture insère la même mesure entre la lecture de
            # existing_keys et cet INSERT. DO NOTHING rend le dépôt idempotent ;
            # RETURNING ne compte que les lignes réellement insérées.
            stmt = (
                insert(Measurement)
                .on_conflict_do_nothing(
                    index_elements=["dataset_id", "room", "measured_at"]
                )
                .returning(Measurement.id)
            )
            inserted = len(session.execute(stmt, params).scalars().all())
        else:
            inserted = 0

        # Un conflit concurrent est un doublon, pas une erreur : on déplace
        # l'écart vers rows_duplicate pour garder
        # rows_total = accepted + rejected + duplicate.
        accepted = inserted
        duplicate = report.rows_duplicate + (report.rows_accepted - inserted)

        ingestion.status = "succeeded"
        ingestion.finished_at = datetime.now(timezone.utc)
        ingestion.rows_total = report.rows_total
        ingestion.rows_accepted = accepted
        ingestion.rows_rejected = report.rows_rejected
        ingestion.rows_duplicate = duplicate
        ingestion.errors = report.errors
        ingestion.error_message = None
        session.commit()
        logger.info(
            "Ingestion %s succeeded: %s accepted, %s rejected, %s duplicate",
            ingestion_id,
            accepted,
            report.rows_rejected,
            duplicate,
        )
        return True
    except ValueError as exc:
        # Refus prévu par le contrat (UTF-8, en-tête, colonnes, bornes, ...).
        session.rollback()
        _mark_failed(session, ingestion_id, str(exc))
        logger.error("Ingestion %s failed: %s", ingestion_id, exc)
        return False
    except Exception:
        # Message générique en base : ni DSN, ni mot de passe, ni requête SQL.
        session.rollback()
        _mark_failed(session, ingestion_id, "Processing error")
        logger.exception("Ingestion %s failed unexpectedly", ingestion_id)
        return False


def _drain_pending() -> int:
    """Traiter tous les dépôts pending disponibles ; renvoyer leur nombre."""
    processed = 0
    while True:
        session = SessionLocal()
        try:
            ingestion = claim_next(session)
            if ingestion is None:
                return processed
            processed += 1
            process(session, ingestion)
        finally:
            session.close()


def main() -> int:
    """--once : vider la file puis sortir ; sinon : boucle avec attente."""
    parser = argparse.ArgumentParser(description="Process CampusData CSV deposits")
    parser.add_argument(
        "--once",
        action="store_true",
        help="process all pending deposits then exit (used by the CronJob)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    interval = _interval_seconds()

    while True:
        try:
            processed = _drain_pending()
            if args.once:
                logger.info("No pending ingestion left; %s processed", processed)
                return 0
        except SQLAlchemyError as exc:
            # En boucle on journalise et on réessaie : aucun pending n'est perdu.
            # Avec --once on rend la main au Job, qui réessaiera (backoffLimit).
            logger.error(
                "Database unavailable (%s); retrying in %ss", type(exc).__name__, interval
            )
            if args.once:
                return 1
        except Exception:
            logger.exception("Unexpected worker error; retrying in %ss", interval)
            if args.once:
                return 1
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
