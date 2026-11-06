#!/bin/sh
# Samples container CPU/RAM and Postgres connections every 5 s while a load test runs.
#   sh tests/load/monitor.sh out.csv &   ...   kill %1
OUT="${1:-monitor.csv}"
echo "time,container,cpu,mem,db_conns,db_active" > "$OUT"
while true; do
  T=$(date +%H:%M:%S)
  C=$(docker compose exec -T db psql -U gnr -d gnr_lms -tAc "select count(*), count(*) filter (where state='active') from pg_stat_activity where datname='gnr_lms'" 2>/dev/null | tr '|' ',')
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' | sed "s#^#$T,#; s#\$#,$C#" >> "$OUT"
  sleep 5
done
