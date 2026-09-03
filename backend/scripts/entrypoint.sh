#!/usr/bin/env bash
set -e

echo "Running Alembic migrations..."
alembic -c backend/alembic.ini upgrade head

if [ "${ADMIN_BOOTSTRAP_ENABLED}" = "true" ]; then
    echo "ADMIN_BOOTSTRAP_ENABLED=true detected. Executing admin bootstrap script..."
    python -m backend.scripts.bootstrap_admin
fi

echo "Starting Uvicorn..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
