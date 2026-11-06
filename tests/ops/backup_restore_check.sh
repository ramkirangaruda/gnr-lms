#!/bin/sh
# Takes a backup with deploy/backup.sh, restores it into a throw-away Postgres container and compares row counts
# table by table, then checks the uploads archive opens. Touches nothing in the running stack except reading it.
#   sh tests/ops/backup_restore_check.sh
set -eu
cd "$(dirname "$0")/../.."
sh deploy/backup.sh
DUMP=$(ls -t backups/db_*.dump | head -1); MEDIA=$(ls -t backups/media_*.tar.gz | head -1)
echo "backup files: $DUMP ($(du -h "$DUMP" | cut -f1)), $MEDIA ($(du -h "$MEDIA" | cut -f1))"
docker rm -f qa-restore >/dev/null 2>&1 || true
docker run -d --name qa-restore -e POSTGRES_PASSWORD=x -e POSTGRES_USER=gnr -e POSTGRES_DB=gnr_lms postgres:16-alpine >/dev/null
until docker exec qa-restore pg_isready -U gnr -d gnr_lms >/dev/null 2>&1; do sleep 1; done; sleep 2
docker exec -i qa-restore pg_restore -U gnr -d gnr_lms --no-owner < "$DUMP"
Q="select string_agg(relname||'='||n_live_tup, ' ' order by relname) from pg_stat_user_tables"
COUNT="select string_agg(t||'='||c, ' ' order by t) from (select 'users' t, count(*) c from accounts_user union all select 'enrol', count(*) from courses_enrollment union all select 'attempts', count(*) from courses_quizattempt union all select 'progress', count(*) from courses_lessonprogress union all select 'doubts', count(*) from courses_doubt union all select 'certs', count(*) from courses_certificate) x"
LIVE=$(docker compose exec -T db psql -U gnr -d gnr_lms -tAc "$COUNT")
REST=$(docker exec qa-restore psql -U gnr -d gnr_lms -tAc "$COUNT")
echo "live:     $LIVE"; echo "restored: $REST"
tar -tzf "$MEDIA" | wc -l | xargs echo "files in uploads archive:"
docker rm -f qa-restore >/dev/null
[ "$LIVE" = "$REST" ] && echo "RESTORE OK: row counts match" || { echo "RESTORE MISMATCH (rows written between backup and check?)"; exit 1; }
