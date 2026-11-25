# CONTEXTE ÉTUDIANT : S3 | contexte de build ./api depuis la racine de votre dépôt
# À PRÉPARER / ADAPTER : Adapter le code copié et fournir APP_VERSION ; ne pas y placer de secret.
# CONTRÔLE ATTENDU : Inspecter UID, version servie et démarrage de la pile après construction.
#
# Étape de préparation : créer les wheels des dépendances verrouillées.
# Le build se lance avec ./api comme contexte ; les chemins COPY en dépendent.
FROM python:3.12-slim-bookworm AS builder
WORKDIR /build
# Copier le lock avant le code permet de réutiliser le cache si seul app/ change.
COPY requirements.lock .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.lock

# Image d’exécution distincte : ne recopier que ce qui sert au fonctionnement.
# Utiliser une base compatible avec les wheels de l’étape builder.
FROM python:3.12-slim-bookworm AS runtime
# Éviter les fichiers .pyc et envoyer les logs sans buffer vers la sortie standard.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# UID stable, repris par le securityContext Kubernetes ; aucun besoin de root.
RUN useradd --uid 10001 --create-home appuser
COPY requirements.lock .
COPY --from=builder /wheels /wheels
# Installer depuis les wheels copiées ; --no-index évite un accès au registre pip.
# Nettoyer le répertoire de travail ; les données du COPY précédent restent
# dans ses couches. Mesurer la taille finale plutôt que supposer un gain.
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.lock \
    && rm -rf /wheels
COPY --chown=10001:10001 app ./app
# Argument de build non secret : transmettre le SHA complet du commit livré.
# Une variable runtime ne remplace pas automatiquement ce fichier VERSION.
ARG APP_VERSION=dev
RUN printf '%s\n' "$APP_VERSION" > /app/app/VERSION
# Toutes les commandes runtime suivantes s’exécutent avec cet utilisateur.
USER 10001:10001
# Documenter le port du processus ; EXPOSE ne publie aucun port sur le poste.
EXPOSE 8000
# Forme JSON : Uvicorn reçoit directement les signaux d’arrêt du conteneur.
# 0.0.0.0 écoute les interfaces du conteneur, pas seulement sa loopback.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
