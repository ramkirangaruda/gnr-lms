#!/bin/sh
# Nightly backup of the database and uploaded files. Run from the project folder on the server:
#   sh deploy/backup.sh
# Schedule it (as the user that runs docker) with `crontab -e`:
#   30 2 * * * cd /home/gnr/gnr-lms && sh deploy/backup.sh >> backups/backup.log 2>&1
# Keeps the last KEEP_DAYS days in ./backups. Copy that folder off the server too (see README).
set -eu
cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y-%m-%d_%H%M)"
mkdir -p backups

# Read POSTGRES_USER / POSTGRES_DB from .env (without sourcing it, so passwords with $ or & are safe)
POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2-)"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2-)"

docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "backups/db_$STAMP.dump"
docker compose exec -T web tar -czf - -C /app media > "backups/media_$STAMP.tar.gz"

find backups -name 'db_*.dump' -mtime +"$KEEP_DAYS" -delete
find backups -name 'media_*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date) backup ok: db_$STAMP.dump media_$STAMP.tar.gz"
