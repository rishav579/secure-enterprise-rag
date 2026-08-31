#!/usr/bin/env bash
set -e

echo "Running Alembic migrations..."
alembic -c backend/alembic.ini upgrade head

echo "Starting Uvicorn..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
