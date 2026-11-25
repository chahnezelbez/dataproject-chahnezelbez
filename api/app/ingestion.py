# CONTEXTE ÉTUDIANT : S2 | contrôles qualité du CSV, sans base ni HTTP
# À PRÉPARER / ADAPTER : règles 4 à 7 écrites sur le modèle des règles 1 à 3 du guide.
# CONTRÔLE ATTENDU : 63/0/0 ; 4/7/1 ; erreurs aux lignes 5-12 ; en-tête invalide refusé.
#
"""Lecture et contrôle qualité des dépôts CSV.

Ce module est pur : ni SQLAlchemy, ni FastAPI, ni psycopg. Il reçoit les
octets bruts et un instant de référence injectable, puis renvoie un rapport
que le worker insérera. Un refus du fichier entier lève ValueError avec la
raison exacte attendue dans error_message.
"""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

HEADER = ("room", "measured_at", "co2_ppm", "temperature_c", "humidity_pct")
MAX_DATA_ROWS = 10_000
MAX_ERRORS = 20
FUTURE_TOLERANCE = timedelta(minutes=5)


class MeasurementRow(NamedTuple):
    """Ligne valide prête à être insérée par le worker."""

    room: str
    measured_at: datetime
    co2_ppm: int
    temperature_c: Decimal
    humidity_pct: Decimal


class IngestionReport(NamedTuple):
    """Rapport pur : lignes valides, compteurs et 20 premières erreurs."""

    rows: list[MeasurementRow]
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    rows_duplicate: int
    errors: list[dict[str, object]]


def _is_blank(row: list[str]) -> bool:
    """Une ligne vide ne compte ni comme acceptée ni comme rejetée."""
    return not row or all(not cell.strip() for cell in row)


def _parse_measured_at(value: str) -> datetime:
    """Règle 3 : ISO 8601 avec fuseau, normalisé en UTC."""
    # fromisoformat accepte aussi "2026-10-06 08:30" : exiger "T" garde
    # le format du contrat et rejette les dates naïves.
    if "T" not in value:
        raise ValueError("Invalid measured_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid measured_at") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Invalid measured_at")
    return parsed.astimezone(timezone.utc)


def _parse_int(value: str, low: int, high: int, reason: str) -> int:
    """Règle 5 : int() refuse "612.5" et "abc" comme attendu."""
    try:
        number = int(value)
    except ValueError:
        raise ValueError(reason) from None
    if not low <= number <= high:
        raise ValueError(reason)
    return number


def _parse_decimal(value: str, low: Decimal, high: Decimal, reason: str) -> Decimal:
    """Règles 6 et 7 : Decimal évite les artefacts de float et Numeric(4,1)."""
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(reason) from None
    if not number.is_finite() or not low <= number <= high:
        raise ValueError(reason)
    return number


def parse_csv(
    text: bytes,
    now: datetime,
    existing_keys: set[tuple[str, datetime]] | None = None,
) -> IngestionReport:
    """Contrôler un fichier CSV et renvoyer ses lignes valides et son rapport."""
    try:
        decoded = text.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("File is not valid UTF-8") from None

    # Déjà filtré par l'API (422), gardé pour un appel direct à la fonction.
    if not decoded:
        raise ValueError("Empty file")

    # now est injecté par les tests : jamais datetime.now() ici.
    reference = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    reader = csv.reader(decoded.splitlines())
    if tuple(next(reader, ())) != HEADER:
        raise ValueError("Invalid header")

    # On garde le numéro physique de ligne, même si des lignes vides sont
    # ignorées : l'en-tête reste la ligne 1 dans les erreurs.
    numbered_rows: list[tuple[int, list[str]]] = []
    for line_number, row in enumerate(reader, start=2):
        if not _is_blank(row):
            numbered_rows.append((line_number, row))

    if not numbered_rows:
        raise ValueError("No data rows")
    if len(numbered_rows) > MAX_DATA_ROWS:
        raise ValueError("Too many rows")

    seen: set[tuple[str, datetime]] = set()
    for room, measured_at in existing_keys or ():
        normalized = (
            measured_at.astimezone(timezone.utc)
            if measured_at.tzinfo is not None
            else measured_at.replace(tzinfo=timezone.utc)
        )
        seen.add((room, normalized))

    rows: list[MeasurementRow] = []
    errors: list[dict[str, object]] = []
    accepted = 0
    rejected = 0
    duplicate = 0

    for line_number, fields in numbered_rows:
        try:
            # Règle 1.
            if len(fields) != 5:
                raise ValueError("Expected 5 columns")

            # Règle 2.
            room = fields[0].strip()
            if not 1 <= len(room) <= 30:
                raise ValueError("Invalid room")

            # Règle 3.
            measured_at = _parse_measured_at(fields[1])

            # Règle 4.
            if measured_at > reference + FUTURE_TOLERANCE:
                raise ValueError("measured_at in the future")

            # Règle 5.
            co2_ppm = _parse_int(fields[2], 250, 10_000, "Invalid co2_ppm")

            # Règle 6.
            temperature_c = _parse_decimal(
                fields[3], Decimal("-30"), Decimal("60"), "Invalid temperature_c"
            )

            # Règle 7.
            humidity_pct = _parse_decimal(
                fields[4], Decimal("0"), Decimal("100"), "Invalid humidity_pct"
            )

            # Un même couple déjà en base ou vu plus haut dans le fichier
            # est un doublon, pas une erreur : la UNIQUE du worker est la
            # protection finale, ici on produit un rapport lisible.
            key = (room, measured_at)
            if key in seen:
                duplicate += 1
                continue
            seen.add(key)
        except ValueError as exc:
            rejected += 1
            if len(errors) < MAX_ERRORS:
                errors.append({"line": line_number, "reason": str(exc)})
            continue

        rows.append(
            MeasurementRow(
                room=room,
                measured_at=measured_at,
                co2_ppm=co2_ppm,
                temperature_c=temperature_c,
                humidity_pct=humidity_pct,
            )
        )
        accepted += 1

    return IngestionReport(
        rows=rows,
        rows_total=len(numbered_rows),
        rows_accepted=accepted,
        rows_rejected=rejected,
        rows_duplicate=duplicate,
        errors=errors,
    )
