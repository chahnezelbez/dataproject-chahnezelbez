# CONTEXTE ÉTUDIANT : S2 | contrôles purs de ingestion.py, sans base
# À PRÉPARER / ADAPTER : garder now injectable pour la règle « date future ».
# CONTRÔLE ATTENDU : 30 rejets / 20 erreurs détaillées ; 2030 rejeté, 2026 accepté.
#
"""Tests unitaires du transformation CSV.

Aucune API, aucun PostgreSQL : ces tests peuvent tourner en quelques
millisecondes et verrouillent les règles de qualité ligne par ligne.
"""

from datetime import datetime, timezone

from app.ingestion import parse_csv

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
HEADER = "room,measured_at,co2_ppm,temperature_c,humidity_pct"


def test_only_first_20_errors_are_detailed():
    """30 lignes invalides donnent 30 rejets mais 20 entrées dans errors."""
    lines = [HEADER]
    lines += ["A101,2026-10-05T08:00:00+02:00,1,20.0,40.0"] * 30
    report = parse_csv("\n".join(lines).encode("utf-8"), NOW)

    assert report.rows_total == 30
    assert report.rows_accepted == 0
    assert report.rows_rejected == 30
    assert report.rows_duplicate == 0
    assert len(report.errors) == 20
    assert all(error["reason"] == "Invalid co2_ppm" for error in report.errors)


def test_future_rule_uses_injected_now():
    """La ligne 2030 est rejetée quelle que soit la date réelle du test."""
    text = "\n".join(
        [
            HEADER,
            "A101,2026-10-05T08:00:00+02:00,712,20.8,46.3",
            "A101,2030-01-01T09:00:00+02:00,710,20.6,47.3",
        ]
    )
    report = parse_csv(text.encode("utf-8"), NOW)

    assert report.rows_total == 2
    assert report.rows_accepted == 1
    assert report.rows_rejected == 1
    assert report.errors == [{"line": 3, "reason": "measured_at in the future"}]


def test_duplicate_inside_same_file_is_not_an_error():
    """Une clé déjà vue dans le fichier compte comme doublon, pas comme erreur."""
    line = "A101,2026-10-05T08:00:00+02:00,712,20.8,46.3"
    report = parse_csv("\n".join([HEADER, line, line]).encode("utf-8"), NOW)

    assert report.rows_total == 2
    assert report.rows_accepted == 1
    assert report.rows_rejected == 0
    assert report.rows_duplicate == 1
    assert report.errors == []
