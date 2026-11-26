"""Consommateur du flux Kafka : contrôle chaque message et enregistre la mesure.

    python -m app.stream      tourne en continu (S2 terminal 4, Compose, Kubernetes)

Les mesures du flux vont dans un jeu dédié, créé au premier message. Le flux y est
suivi comme un dépôt permanent nommé « kafka:<topic> », toujours succeeded : ses
compteurs augmentent à chaque message, et l'interface l'affiche comme les autres dépôts.
"""
import csv
import io
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaException, TopicPartition
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ingestion import (
    HEADER as EXPECTED_HEADER,
)
from app.ingestion import (
    MAX_ERRORS as MAX_DETAILED_ERRORS,
)
from app.ingestion import parse_csv
from app.models import Dataset, Ingestion, Measurement

TOPIC = os.environ.get("KAFKA_TOPIC", "campus.measurements")
DATASET_NAME = os.environ.get("STREAM_DATASET_NAME", "Flux capteurs (Kafka)")
STREAM_FILENAME = f"kafka:{TOPIC}"
RETRY_SECONDS = 5

log = logging.getLogger("stream")


def check_line(fields: list[str], now: datetime) -> dict[str, object]:
    """Réutiliser les règles 2 à 7 de parse_csv : ingestion.py n'expose pas check_line."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(fields)
    text = ",".join(EXPECTED_HEADER) + "\n" + buffer.getvalue()
    report = parse_csv(text.encode("utf-8"), now)
    if report.rows_rejected:
        raise ValueError(str(report.errors[0]["reason"]))
    return dict(report.rows[0]._asdict())


def parse_message(raw: bytes | None, now: datetime) -> dict:
    """Contrôler un message. Renvoie la mesure, ou lève ValueError avec la raison."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):  # message vide, octets non UTF-8, texte qui n'est pas du JSON
        raise ValueError("Invalid message") from None
    if not isinstance(data, dict) or set(data) != set(EXPECTED_HEADER):
        raise ValueError("Invalid message")
    # Mêmes règles 2 à 7 que pour une ligne de CSV : on réutilise check_line.
    return check_line([str(data[key]) for key in EXPECTED_HEADER], now)


def stream_ingestion(session: Session) -> Ingestion:
    """Trouver, ou créer au premier message, le jeu du flux et son dépôt permanent."""
    query = select(Dataset).where(Dataset.name == DATASET_NAME).with_for_update()
    dataset = session.scalars(query).first()
    if dataset is None:
        # ON CONFLICT : si un autre consommateur vient de créer le jeu, on garde le sien.
        session.execute(
            insert(Dataset)
            .values(name=DATASET_NAME, owner="Capteurs", description=f"Mesures reçues du topic {TOPIC}")
            .on_conflict_do_nothing(index_elements=["name"])
        )
        dataset = session.scalars(query).one()
    ingestion = session.scalars(
        select(Ingestion).where(Ingestion.dataset_id == dataset.id, Ingestion.filename == STREAM_FILENAME)
    ).first()
    if ingestion is None:
        now = datetime.now(timezone.utc)
        ingestion = Ingestion(
            dataset_id=dataset.id,
            filename=STREAM_FILENAME,
            content=b"",  # pas de fichier : les mesures arrivent une par une
            status="succeeded",  # jamais pending : le worker et la relance l'ignorent
            rows_total=0,
            rows_accepted=0,
            rows_rejected=0,
            rows_duplicate=0,
            errors=[],
            started_at=now,
        )
        session.add(ingestion)
        session.flush()  # obtenir ingestion.id avant d'insérer la mesure
    return ingestion


def handle(raw: bytes | None, now: datetime | None = None) -> str:
    """Traiter un message dans UNE transaction. Renvoie accepted, duplicate ou la raison du rejet."""
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as session:
        ingestion = stream_ingestion(session)
        ingestion.rows_total += 1
        try:
            row = parse_message(raw, now)
        except ValueError as error:
            outcome = str(error)
            ingestion.rows_rejected += 1
            if len(ingestion.errors) < MAX_DETAILED_ERRORS:
                # Pour le flux, « line » est le numéro du message reçu (1, 2, 3...).
                ingestion.errors = [*ingestion.errors, {"line": ingestion.rows_total, "reason": outcome}]
        else:
            # Même contrainte UNIQUE que pour les fichiers : un message reçu deux fois
            # (doublon du capteur ou relecture Kafka) n'est jamais inséré deux fois.
            inserted = session.execute(
                insert(Measurement)
                .values(**row, dataset_id=ingestion.dataset_id, ingestion_id=ingestion.id)
                .on_conflict_do_nothing(index_elements=["dataset_id", "room", "measured_at"])
                .returning(Measurement.id)
            ).first()
            if inserted is None:
                outcome = "duplicate"
                ingestion.rows_duplicate += 1
            else:
                outcome = "accepted"
                ingestion.rows_accepted += 1
        ingestion.finished_at = datetime.now(timezone.utc)  # heure du dernier message traité
        session.commit()  # mesure et compteurs validés ensemble
    return outcome


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
    consumer = Consumer(
        {
            "bootstrap.servers": servers,
            # Les consommateurs d'un même groupe se partagent les partitions du topic,
            # et Kafka retient pour ce groupe la position (offset) du dernier message validé.
            "group.id": os.environ.get("KAFKA_GROUP_ID", "campus-stream"),
            # Premier démarrage du groupe : lire le topic depuis le début.
            "auto.offset.reset": "earliest",
            # On valide l'offset nous-mêmes, APRÈS le COMMIT SQL (voir plus bas).
            "enable.auto.commit": False,
            # Créer le topic s'il n'existe pas encore (consommateur lancé avant le simulateur).
            "allow.auto.create.topics": True,
        }
    )
    consumer.subscribe([TOPIC])
    stopping: list[bool] = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    log.info("lecture du topic %s sur %s", TOPIC, servers)
    try:
        while not stopping:
            message = consumer.poll(1.0)  # attendre un message au plus 1 s
            if message is None:
                continue
            if message.error():
                # Kafka absent, topic en cours de création... : le client réessaie seul.
                log.warning("kafka : %s", message.error())
                continue
            try:
                outcome = handle(message.value())
            except (OperationalError, ProgrammingError):
                # Base indisponible ou tables absentes : on ne valide pas l'offset et on
                # se replace sur ce message pour le relire au prochain essai. Rien n'est perdu.
                log.error("base indisponible, message relu dans %s s", RETRY_SECONDS)
                consumer.seek(TopicPartition(message.topic(), message.partition(), message.offset()))
                time.sleep(RETRY_SECONDS)
                continue
            # Valider l'offset seulement maintenant : en cas d'arrêt brutal entre les deux
            # COMMIT, le message est relu au redémarrage et compté en doublon (au moins une fois).
            try:
                consumer.commit(message=message, asynchronous=False)
            except KafkaException as error:
                # Kafka coupé à cet instant : la position sera validée avec le message suivant.
                log.warning("offset non validé (%s)", error)
            log.info(
                "message partition %s offset %s : %s", message.partition(), message.offset(), outcome
            )
    except KeyboardInterrupt:
        pass  # Ctrl+C dans le terminal
    finally:
        consumer.close()  # quitter le groupe proprement : les partitions sont réattribuées
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
