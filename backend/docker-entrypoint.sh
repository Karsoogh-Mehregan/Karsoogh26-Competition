#!/bin/sh
set -eu

if [ "${COLLECTSTATIC:-1}" = "1" ]; then
    echo "entrypoint: collecting static files"
    python manage.py collectstatic --noinput
fi

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "entrypoint: applying migrations"
    python manage.py migrate --noinput
fi

GRAPH_DATA_FILE="${GRAPH_DATA_FILE:-/app/graph_data.json}"

if [ "${IMPORT_GRAPH:-1}" = "1" ]; then
    if [ -f "${GRAPH_DATA_FILE}" ]; then
        for board in ${GRAPH_BOARDS:-girls boys}; do
            echo "entrypoint: importing graph from ${GRAPH_DATA_FILE} into ${board}"
            python manage.py import_graph --board "${board}" --file "${GRAPH_DATA_FILE}"
        done
    else
        echo "entrypoint: no ${GRAPH_DATA_FILE}, skipping import_graph"
    fi
fi

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    python - <<'PYEOF'
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]

if User.objects.filter(username=username).exists():
    print(f"entrypoint: superuser {username} already exists")
else:
    User.objects.create_superuser(
        username=username,
        email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
        password=os.environ["DJANGO_SUPERUSER_PASSWORD"],
    )
    print(f"entrypoint: created superuser {username}")
PYEOF
fi

WORKERS="${WEB_CONCURRENCY:-3}"
HOST="${UVICORN_HOST:-0.0.0.0}"
PORT="${UVICORN_PORT:-8000}"
LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"

echo "entrypoint: uvicorn, ${WORKERS} workers on ${HOST}:${PORT}"
exec uvicorn core.asgi:application \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}" \
    --lifespan off
