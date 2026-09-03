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
