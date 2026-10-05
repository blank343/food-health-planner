#!/bin/sh
# Startskript des Containers: Datenbank-Migrationen ausführen, dann die App starten.
# Migrationen sind idempotent (nur fehlende Schritte). Steuerbar über FHP_RUN_MIGRATIONS=0.
set -e

if [ "${FHP_RUN_MIGRATIONS:-1}" = "1" ]; then
  tries=0
  until alembic upgrade head; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
      echo "Datenbank-Migration nach 30 Versuchen fehlgeschlagen. Ist die Datenbank erreichbar und das Passwort korrekt?" >&2
      exit 1
    fi
    echo "Datenbank noch nicht bereit, neuer Versuch ($tries/30) ..."
    sleep 2
  done
fi

exec "$@"
