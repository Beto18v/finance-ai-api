#!/bin/sh
set -eu

exec gunicorn \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WEB_CONCURRENCY:-1}" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout "${GUNICORN_TIMEOUT:-600}" \
  --access-logfile '-' \
  --error-logfile '-' \
  app.main:app
