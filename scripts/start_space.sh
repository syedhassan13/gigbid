#!/bin/sh
# Entrypoint of the single-container deployment.
set -e
mkdir -p /data/var
[ -d /data/var/models ] || cp -r /app/var/models /data/var/models 2>/dev/null || true
if [ ! -f /app/data/processed/stream_jobs.jsonl ]; then
  python scripts/prepare_data.py   # synthetic + committed stats; Kaggle raw data is not shipped in the image
fi
uvicorn gigsim.app:app --host 127.0.0.1 --port 8100 &
sleep 3
exec uvicorn apps.api.main:app --host 0.0.0.0 --port "${PORT:-7860}"
