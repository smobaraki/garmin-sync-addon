#!/usr/bin/env bash
set -euo pipefail

OPTIONS=/data/options.json
STATE_FILE=/data/.garmin_sync_initialized

export GARMIN_EMAIL=$(jq -r '.garmin_email // empty' "$OPTIONS")
export GARMIN_USERNAME="$GARMIN_EMAIL"
export GARMIN_PASSWORD=$(jq -r '.garmin_password // empty' "$OPTIONS")
export DATABASE_URL=$(jq -r '.database_url // empty' "$OPTIONS")
INTERVAL=$(jq -r '.sync_interval_min // 30' "$OPTIONS")
START_DATE=$(jq -r '.start_date // empty' "$OPTIONS")
DATA_TYPES=$(jq -r '.data_types // empty' "$OPTIONS")

TOKEN_JSON=$(jq -r '.garmin_token_json // empty' "$OPTIONS")
if [ -n "$TOKEN_JSON" ] && [ "$TOKEN_JSON" != "null" ]; then
  export GARMIN_TOKEN_JSON="$TOKEN_JSON"
fi

export GARMIN_TOKEN_DIR=/data/.garminconnect
mkdir -p "$GARMIN_TOKEN_DIR"

TODAY=$(date +%Y-%m-%d)

if [ -n "$START_DATE" ] && [ "$START_DATE" != "null" ] && [ ! -f "$STATE_FILE" ]; then
  ARGS="--start-date $START_DATE --end-date $TODAY"
  echo "=== First run — backfilling from $START_DATE to $TODAY ==="
else
  ARGS="--start-date $TODAY --end-date $TODAY"
  echo "=== Routine sync for $TODAY ==="
fi

if [ -n "$DATA_TYPES" ] && [ "$DATA_TYPES" != "null" ]; then
  ARGS="$ARGS --data-types $DATA_TYPES"
fi

echo "Interval: ${INTERVAL} min"
echo "DB: ${DATABASE_URL%%@*}@***"
echo ""

while true; do
  echo "[$(date -Iseconds)] Running ETL..."
  python -m garmin_health_data.cli extract $ARGS
  touch "$STATE_FILE"
  echo "[$(date -Iseconds)] Sync done. Sleeping ${INTERVAL} min..."
  sleep $((INTERVAL * 60))
done
