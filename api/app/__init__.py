"""Package de l’API CampusData.

Ce fichier permet d’identifier le package app. Il reste sans effet de démarrage :
ne pas lancer Uvicorn, ouvrir une transaction ou créer le schéma lors de l’import.
Points d’entrée : app.main:app (API) ; en S2, app.init_db (schéma) et app.worker (ingestion).
"""
