#!/usr/bin/env bash
set -euo pipefail

OPTIONS=/data/options.json
STATE_FILE=/data/.garmin_sync_initialized
BACKFILL_FILE=/data/.garmin_sync_backfill_done

export GARMIN_EMAIL=$(jq -r '.garmin_email // empty' "$OPTIONS")
export GARMIN_USERNAME="$GARMIN_EMAIL"
export GARMIN_PASSWORD=$(jq -r '.garmin_password // empty' "$OPTIONS")
export DATABASE_URL=$(jq -r '.database_url // empty' "$OPTIONS")
MODE=$(jq -r '.mode // "routine"' "$OPTIONS")
INTERVAL=$(jq -r '.sync_interval_min // 30' "$OPTIONS")
BACKFILL_START=$(jq -r '.backfill_start // empty' "$OPTIONS")
DATA_TYPES=$(jq -r '.data_types // empty' "$OPTIONS")

TOKEN_JSON=$(jq -r '.garmin_token_json // empty' "$OPTIONS")
if [ -n "$TOKEN_JSON" ] && [ "$TOKEN_JSON" != "null" ]; then
  export GARMIN_TOKEN_JSON="$TOKEN_JSON"
fi

export GARMIN_TOKEN_DIR=/data/.garminconnect
mkdir -p "$GARMIN_TOKEN_DIR"

TODAY=$(date +%Y-%m-%d)

case "$MODE" in
  auth)
    echo "=== Auth mode — logging in and saving tokens ==="
    python -m garmin_health_data.cli auth
    echo "Tokens saved to /data/.garminconnect/"
    echo "Copy token content into garmin_token_json field, then switch mode to routine."
    exit 0
    ;;
  backfill)
    if [ ! -f "$BACKFILL_FILE" ] && [ -n "$BACKFILL_START" ] && [ "$BACKFILL_START" != "null" ]; then
      ARGS="--start-date $BACKFILL_START --end-date $TODAY"
      echo "=== Backfill mode — $BACKFILL_START → $TODAY ==="
    else
      ARGS="--start-date $TODAY --end-date $TODAY"
      echo "=== Backfill already completed — routine sync for $TODAY ==="
    fi
    ;;
  *)
    ARGS="--start-date $TODAY --end-date $TODAY"
    echo "=== Routine mode — syncing $TODAY ==="
    ;;
esac

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

  if [ "$MODE" = "backfill" ] && [ ! -f "$BACKFILL_FILE" ] && [ -n "$BACKFILL_START" ] && [ "$BACKFILL_START" != "null" ]; then
    touch "$BACKFILL_FILE"
    ARGS="--start-date $TODAY --end-date $TODAY"
    echo "[$(date -Iseconds)] Backfill complete. Now syncing $TODAY only."
    if [ -n "$DATA_TYPES" ] && [ "$DATA_TYPES" != "null" ]; then
      ARGS="$ARGS --data-types $DATA_TYPES"
    fi
  fi

  echo "[$(date -Iseconds)] Sync done. Sleeping ${INTERVAL} min..."
  sleep $((INTERVAL * 60))
done
