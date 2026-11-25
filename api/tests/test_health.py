# CONTEXTE ÉTUDIANT : S1-S2 | tests lancés dans votre environnement Python
# À PRÉPARER / ADAPTER : Définir DATABASE_URL avant pytest ; réserver campus_test aux tests métier.
# CONTRÔLE ATTENDU : Lire le nombre de tests et les assertions : deux tests ne valident ni l'API métier ni l'ingestion.
#
"""Tests de fumée du starter, à compléter par la recette métier en séance 2.

DATABASE_URL doit être définie avant l'import de app.main, même si ces deux
routes n'interrogent pas PostgreSQL. Les tests métier utilisent campus_test.
Ne jamais réinitialiser une base dont le nom ne termine pas par _test.
"""
from fastapi.testclient import TestClient

from app.main import app

# TestClient appelle l'application dans le processus de test, sans lancer
# Uvicorn, Nginx, Docker ou un serveur TCP. Un succès ici ne teste pas le réseau.
client = TestClient(app)


def test_liveness():
    """Le contrat minimal de santé du processus reste disponible sans SQL."""
    assert client.get("/health/live").json() == {"status": "ok"}


def test_version():
    """La route de version expose la clé attendue par la vérification release."""
    assert "version" in client.get("/api/version").json()

# TODO S2 : compléter avec les tests métier sur PostgreSQL (campus_test).
# Organiser chaque scénario en préparation, action, vérification observable.
# Ingestion : utiliser les fichiers de data/ et vérifier les compteurs
# acceptées / rejetées / doublons, puis l'absence de doublon après un second dépôt.
# Suppression d'un jeu : 204 sans corps, puis 404 et plus aucune mesure liée.
# Readiness : tester DB absente et table absente indépendamment.
# Ces deux tests seuls ne valident ni persistance, ni métier, ni déploiement.
