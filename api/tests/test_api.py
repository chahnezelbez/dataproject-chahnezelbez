# CONTEXTE ÉTUDIANT : S2 | tests API et worker sur campus_test
# À PRÉPARER / ADAPTER : lancer init_db sur campus_test avant pytest.
# CONTRÔLE ATTENDU : F01-F12, F13-F16, F20-F24 ; 409 sur relance non failed.
#
"""Tests d'acceptation de l'API CampusData.

Chaque test suit préparation → action → vérification observable. Les appels
passent par TestClient : aucun curl, aucun serveur TCP, mais la vraie base
campus_test et le vrai worker appelé directement avec NOW injecté.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

REFERENCE = "mesures-salles-2026-10-05.csv"
ERRORS_FILE = "mesures-avec-erreurs.csv"
BAD_HEADER = "en-tete-invalide.csv"
COUNTERS = (
    "rows_total",
    "rows_accepted",
    "rows_rejected",
    "rows_duplicate",
)


def _ingestion(client, ingestion_id):
    """Lire un dépôt et vérifier que la route répond 200."""
    response = client.get(f"/api/ingestions/{ingestion_id}")
    assert response.status_code == 200
    return response.json()


def _counters(body):
    """Extraire les quatre compteurs dans l'ordre du contrat."""
    return tuple(body[name] for name in COUNTERS)


def test_create_dataset_defaults_and_trims_name(client):
    """F01/F02 : nom normalisé, owner par défaut, compteur à zéro."""
    response = client.post("/api/datasets", json={"name": "  Salles B  "})

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["name"] == "Salles B"
    assert body["description"] is None
    assert body["owner"] == "Équipe"
    assert body["measurement_count"] == 0
    assert body["created_at"].endswith("Z")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "   "},
        {"name": "ab"},
        {"name": "a" * 121},
        {"name": "Salle A", "owner": None},
        {"name": "Salle A", "owner": "x"},
        {"name": "Salle A", "owner": "x" * 61},
        {"name": "Salle A", "id": str(uuid4())},
        {"name": "Salle A", "measurement_count": 0},
    ],
)
def test_invalid_dataset_payloads_create_nothing(client, payload):
    """F03/F04 : validation Pydantic, aucun jeu persisté."""
    response = client.post("/api/datasets", json=payload)

    assert response.status_code == 422
    assert client.get("/api/datasets").json() == []


def test_duplicate_dataset_name(client):
    """F05 : conflit de nom unique, un seul jeu en base."""
    assert client.post("/api/datasets", json={"name": "Salle A"}).status_code == 201

    response = client.post("/api/datasets", json={"name": "Salle A"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Dataset name already exists"}
    assert len(client.get("/api/datasets").json()) == 1


def test_list_datasets_empty_then_ordered(client):
    """F06 : liste vide puis ordre de création décroissant."""
    assert client.get("/api/datasets").json() == []

    first = client.post("/api/datasets", json={"name": "Première salle"}).json()
    second = client.post("/api/datasets", json={"name": "Deuxième salle"}).json()

    ids = [item["id"] for item in client.get("/api/datasets").json()]
    assert ids == [second["id"], first["id"]]


def test_get_dataset_unknown_or_malformed_id(client):
    """F07/F12 : UUID inconnu en 404, chaîne non UUID en 422."""
    assert client.get(f"/api/datasets/{uuid4()}").status_code == 404
    assert client.get("/api/datasets/pas-un-uuid").status_code == 422


def test_upload_reference_returns_pending_without_content(client, dataset, upload):
    """F10 : 202, Location, compteurs null et jamais de champ content."""
    response = upload(dataset["id"], REFERENCE)

    assert response.status_code == 202
    assert response.headers["Location"].startswith("/api/ingestions/")
    body = response.json()
    assert body["status"] == "pending"
    assert _counters(body) == (None, None, None, None)
    assert "content" not in body


@pytest.mark.parametrize(
    ("content", "content_type", "params", "expected"),
    [
        (b"", "text/csv", {"filename": "x.csv"}, 422),
        (b"room,room\nA,A\n", "application/json", {"filename": "x.csv"}, 415),
        (b"x" * 1_048_577, "text/csv", {"filename": "x.csv"}, 413),
        (b"room,room\nA,A\n", "text/csv", {}, 422),
        (b"room,room\nA,A\n", "text/csv", {"filename": "a/b.csv"}, 422),
    ],
)
def test_upload_rejections_create_no_ingestion(
    client, dataset, content, content_type, params, expected
):
    """F11 : 422, 415, 413, 422 dans l'ordre, sans aucun dépôt créé."""
    response = client.post(
        f"/api/datasets/{dataset['id']}/ingestions",
        params=params,
        content=content,
        headers={"Content-Type": content_type},
    )

    assert response.status_code == expected
    assert client.get(f"/api/datasets/{dataset['id']}/ingestions").json() == []


def test_upload_to_missing_dataset(client, data_file):
    """F12 : le jeu absent est recherché après les contrôles du corps."""
    response = client.post(
        f"/api/datasets/{uuid4()}/ingestions",
        params={"filename": REFERENCE},
        content=data_file(REFERENCE),
        headers={"Content-Type": "text/csv"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found"}


def test_process_reference_file(client, dataset, upload, process_pending, session):
    """F13/F25 : 63 mesures persistées, dates cohérentes, somme exacte."""
    ingestion = upload(dataset["id"], REFERENCE).json()
    process_pending()

    body = _ingestion(client, ingestion["id"])
    assert body["status"] == "succeeded"
    assert _counters(body) == (63, 63, 0, 0)
    assert body["started_at"] <= body["finished_at"]
    assert (
        client.get(f"/api/datasets/{dataset['id']}").json()["measurement_count"] == 63
    )
    total = session.execute(text("SELECT sum(co2_ppm) FROM measurements")).scalar_one()
    assert total == 46504


def test_process_error_file_reports_each_reason(
    client, dataset, upload, process_pending
):
    """F14 : 4 acceptées, 7 rejetées, 1 doublon, raisons du contrat."""
    ingestion = upload(dataset["id"], ERRORS_FILE).json()
    process_pending()

    body = _ingestion(client, ingestion["id"])
    assert body["status"] == "succeeded"
    assert _counters(body) == (12, 4, 7, 1)
    assert body["errors"] == [
        {"line": 5, "reason": "Invalid co2_ppm"},
        {"line": 6, "reason": "Invalid humidity_pct"},
        {"line": 7, "reason": "Invalid measured_at"},
        {"line": 8, "reason": "Invalid room"},
        {"line": 9, "reason": "measured_at in the future"},
        {"line": 10, "reason": "Invalid temperature_c"},
        {"line": 12, "reason": "Expected 5 columns"},
    ]


def test_second_upload_is_idempotent(client, dataset, upload, process_pending):
    """F15 : second dépôt identique, 63 doublons, compteur inchangé."""
    upload(dataset["id"], REFERENCE)
    process_pending()
    second = upload(dataset["id"], REFERENCE).json()
    process_pending()

    body = _ingestion(client, second["id"])
    assert body["status"] == "succeeded"
    assert _counters(body) == (63, 0, 0, 63)
    assert (
        client.get(f"/api/datasets/{dataset['id']}").json()["measurement_count"] == 63
    )


def test_invalid_header_fails_without_measurement(
    client, dataset, upload, process_pending, session
):
    """F16 : en-tête invalide, error_message exact, aucune mesure."""
    ingestion = upload(dataset["id"], BAD_HEADER).json()
    process_pending()

    body = _ingestion(client, ingestion["id"])
    assert body["status"] == "failed"
    assert body["error_message"] == "Invalid header"
    assert session.execute(text("SELECT count(*) FROM measurements")).scalar_one() == 0


def test_retry_failed_then_conflict(client, dataset, upload, process_pending):
    """F20/F21 : relance failed → 200 pending, puis 409 sur pending."""
    ingestion = upload(dataset["id"], BAD_HEADER).json()
    process_pending()
    assert _ingestion(client, ingestion["id"])["status"] == "failed"

    response = client.post(f"/api/ingestions/{ingestion['id']}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert _counters(body) == (None, None, None, None)
    assert body["errors"] == []
    assert body["error_message"] is None
    assert body["started_at"] is None
    assert body["finished_at"] is None

    conflict = client.post(f"/api/ingestions/{ingestion['id']}/retry")
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Ingestion cannot be retried"}


def test_retry_succeeded_is_rejected(client, dataset, upload, process_pending):
    """F21 : un dépôt succeeded ne peut pas être relancé."""
    ingestion = upload(dataset["id"], REFERENCE).json()
    process_pending()

    response = client.post(f"/api/ingestions/{ingestion['id']}/retry")

    assert response.status_code == 409
    assert response.json() == {"detail": "Ingestion cannot be retried"}


def test_list_ingestions_filter_and_unknown_status(
    client, dataset, upload, process_pending
):
    """F22 : filtre status=failed et 422 FastAPI sur statut inconnu."""
    good = upload(dataset["id"], REFERENCE).json()
    bad = upload(dataset["id"], BAD_HEADER).json()
    process_pending()

    response = client.get(
        f"/api/datasets/{dataset['id']}/ingestions",
        params={"status": "failed"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [bad["id"]]
    assert good["id"] not in [item["id"] for item in response.json()]
    assert (
        client.get(
            f"/api/datasets/{dataset['id']}/ingestions",
            params={"status": "inconnu"},
        ).status_code
        == 422
    )


def test_stats_filters_and_invalid_period(client, dataset, upload, process_pending):
    """F23/F24 : agrégats SQL, filtres, 422 période, rooms vide."""
    upload(dataset["id"], REFERENCE)
    process_pending()

    response = client.get(f"/api/datasets/{dataset['id']}/stats")
    assert response.status_code == 200
    body = response.json()
    assert [room["room"] for room in body["rooms"]] == ["A101", "A102", "B201"]
    a101 = body["rooms"][0]
    assert a101["measurements"] == 21
    assert a101["co2_avg"] == 636.1
    assert a101["co2_min"] == 430
    assert a101["co2_max"] == 1092
    assert next(r for r in body["rooms"] if r["room"] == "A102")["co2_max"] == 1304
    assert next(r for r in body["rooms"] if r["room"] == "B201")["co2_max"] == 1572

    only_a101 = client.get(
        f"/api/datasets/{dataset['id']}/stats", params={"room": "A101"}
    )
    assert len(only_a101.json()["rooms"]) == 1

    invalid = client.get(
        f"/api/datasets/{dataset['id']}/stats",
        params={"from": "2026-10-06T00:00:00Z", "to": "2026-10-05T00:00:00Z"},
    )
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "Invalid period"}

    empty = client.post("/api/datasets", json={"name": "Salle vide"}).json()
    empty_stats = client.get(f"/api/datasets/{empty['id']}/stats")
    assert empty_stats.json()["rooms"] == []


def test_delete_dataset_removes_children(
    client, dataset, upload, process_pending, session
):
    """F08/F09 : 204 sans corps, cascade DB, puis 404 sur le jeu supprimé."""
    upload(dataset["id"], REFERENCE)
    process_pending()

    response = client.delete(f"/api/datasets/{dataset['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/datasets/{dataset['id']}").status_code == 404
    for table in ("datasets", "ingestions", "measurements"):
        count = session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        assert count == 0
    assert client.delete(f"/api/datasets/{uuid4()}").status_code == 404


def test_unknown_ingestion_and_malformed_id(client):
    """F12/F07 : ingestion absente en 404, UUID mal formé en 422."""
    assert client.get(f"/api/ingestions/{uuid4()}").status_code == 404
    assert client.get("/api/ingestions/pas-un-uuid").status_code == 422
