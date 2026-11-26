#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "Dossier du projet : $PROJECT_DIR"

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Erreur : fichier .env introuvable dans $PROJECT_DIR." >&2
  echo "Créez-le à partir de .env.example puis renseignez les valeurs." >&2
  exit 1
fi

if [ ! -f "$PROJECT_DIR/compose.dev.yaml" ]; then
  echo "Erreur : compose.dev.yaml introuvable dans $PROJECT_DIR." >&2
  exit 1
fi

if [ ! -d "$PROJECT_DIR/api" ]; then
  echo "Erreur : dossier api/ introuvable dans $PROJECT_DIR." >&2
  exit 1
fi

if [ ! -f "$PROJECT_DIR/.venv/bin/activate" ]; then
  echo "Erreur : environnement virtuel .venv introuvable." >&2
  echo "Créez-le puis installez api/requirements-dev.lock avant de relancer." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Erreur : docker est introuvable dans le PATH." >&2
  exit 1
fi

echo "Activation de l'environnement virtuel..."
source "$PROJECT_DIR/.venv/bin/activate"
echo "Environnement virtuel activé."

echo "Chargement des variables depuis .env..."
set -a
source "$PROJECT_DIR/.env"
set +a

for var in POSTGRES_USER POSTGRES_DB POSTGRES_PASSWORD; do
  if [ -z "${!var:-}" ]; then
    echo "Erreur : la variable $var est absente ou vide dans .env." >&2
    exit 1
  fi
done
echo "Variables chargées."

echo "Démarrage de la base de données..."
docker compose -f compose.dev.yaml up -d db

echo "Attente que la base de données soit healthy..."
attempt=1
max_attempts=60
while [ "$attempt" -le "$max_attempts" ]; do
  db_container="$(docker compose -f compose.dev.yaml ps -q db)"
  db_status=""
  if [ -n "$db_container" ]; then
    db_status="$(docker inspect --format '{{.State.Health.Status}}' "$db_container" 2>/dev/null || true)"
  fi

  if [ "$db_status" = "healthy" ]; then
    echo "Base prête !"
    break
  fi

  echo "Base pas encore prête (statut : ${db_status:-indisponible}). Nouvelle vérification dans 2 s..."
  sleep 2
  attempt=$((attempt + 1))

  if [ "$attempt" -gt "$max_attempts" ]; then
    echo "Erreur : la base n'est pas devenue healthy après $((max_attempts * 2)) s." >&2
    docker compose -f compose.dev.yaml ps db >&2
    exit 1
  fi
done

echo "Démarrage de l'interface web..."
docker compose -f compose.dev.yaml up -d web
echo "Interface web démarrée sur http://127.0.0.1:8080"

echo "Configuration de DATABASE_URL pour l'API locale..."
export DATABASE_URL="postgresql+psycopg://campus:${POSTGRES_PASSWORD}@127.0.0.1:5432/campus"
echo "DATABASE_URL configurée."

echo "Démarrage de l'API sur http://127.0.0.1:8000..."
cd "$PROJECT_DIR/api"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
