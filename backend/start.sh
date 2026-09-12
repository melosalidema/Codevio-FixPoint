#!/bin/sh
# Production entrypoint: migrate first, then serve.
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting Fixpoint on port ${PORT:-8000}..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
