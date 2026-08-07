#!/bin/sh
# Arranque del contenedor.
#
# Se lanzan dos cosas en la MISMA máquina a propósito: la base de datos es un
# SQLite sobre un volumen, y un volumen solo se monta en una máquina. Separar
# la tarea de anclaje en otra máquina significaría otra base de datos.
#
# La tarea va en segundo plano; si se muere, /health lo delata porque la marca
# last_upgrade_run deja de actualizarse.

set -e

echo "[start] anclaje cada ${UPGRADE_INTERVAL:-7200}s en segundo plano"
python upgrade_job.py --loop "${UPGRADE_INTERVAL:-7200}" &

echo "[start] servidor web en :8080"
exec gunicorn \
  --bind 0.0.0.0:8080 \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  app:app
