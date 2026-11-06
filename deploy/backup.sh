#!/bin/sh
# Nightly backup of the database and uploaded files. Run from the project folder on the server:
#   sh deploy/backup.sh
# Schedule it (as the user that runs docker) with `crontab -e`:
#   30 2 * * * cd /home/gnr/gnr-lms && sh deploy/backup.sh >> backups/backup.log 2>&1
#
# Keeps the last KEEP_DAYS days in ./backups on this server, AND copies them off the server when
# BACKUP_REMOTE is set in .env (an rclone remote such as "b2:gnr-lms-backups" or "gdrive:gnr-lms-backups";
# set it up once with `rclone config`, see README → Backups). A backup that only lives on the server
# is lost with the server, so set BACKUP_REMOTE before launch.
set -eu
cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-7}"
STAMP="$(date +%Y-%m-%d_%H%M)"
mkdir -p backups

# Read settings from .env (without sourcing it, so passwords with $ or & are safe)
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
POSTGRES_USER="$(envval POSTGRES_USER)"
POSTGRES_DB="$(envval POSTGRES_DB)"
BACKUP_REMOTE="${BACKUP_REMOTE:-$(envval BACKUP_REMOTE)}"

docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "backups/db_$STAMP.dump.part"
mv "backups/db_$STAMP.dump.part" "backups/db_$STAMP.dump"
# Lesson MP4s are large and rarely change, so the nightly archive skips them; they are mirrored separately below.
docker compose exec -T web tar -czf - -C /app --exclude=media/lessons/videos media > "backups/media_$STAMP.tar.gz.part"
mv "backups/media_$STAMP.tar.gz.part" "backups/media_$STAMP.tar.gz"

find backups -name 'db_*.dump' -mtime +"$KEEP_DAYS" -delete
find backups -name 'media_*.tar.gz' -mtime +"$KEEP_DAYS" -delete

if [ -n "$BACKUP_REMOTE" ]; then
  rclone copy backups "$BACKUP_REMOTE/nightly" --include 'db_*.dump' --include 'media_*.tar.gz' --max-age 48h
  # one copy of any lesson MP4s on the server, replaced each night (empty when videos are on Bunny Stream)
  docker compose exec -T web tar -cf - -C /app/media lessons/videos 2>/dev/null | rclone rcat "$BACKUP_REMOTE/videos/videos_latest.tar" || true
  echo "$(date) copied off-server to $BACKUP_REMOTE"
else
  echo "$(date) WARNING: BACKUP_REMOTE not set, backups exist only on this server"
fi
echo "$(date) backup ok: db_$STAMP.dump media_$STAMP.tar.gz"
