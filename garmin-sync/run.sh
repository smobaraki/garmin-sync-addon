#!/usr/bin/env bash
set -euo pipefail

OPTIONS=/data/options.json
STATE_FILE=/data/.garmin_sync_initialized

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
    exit 0
    ;;
  backfill)
    if [ -n "$BACKFILL_START" ] && [ "$BACKFILL_START" != "null" ]; then
      BF_FILE="/data/.garmin_backfill_${BACKFILL_START}"
      if [ ! -f "$BF_FILE" ]; then
        ARGS="--start-date $BACKFILL_START --end-date $TODAY"
        echo "=== Backfill — $BACKFILL_START → $TODAY ==="
      else
        ARGS="--start-date $TODAY --end-date $TODAY"
        echo "=== Backfill $BACKFILL_START already done — routine $TODAY ==="
      fi
    else
      ARGS="--start-date $TODAY --end-date $TODAY"
      echo "=== Backfill mode but no start date — routine $TODAY ==="
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

  if [ "$MODE" = "backfill" ] && [ -n "${BF_FILE:-}" ] && [ ! -f "${BF_FILE:-}" ]; then
    touch "$BF_FILE"
    ARGS="--start-date $TODAY --end-date $TODAY"
    if [ -n "$DATA_TYPES" ] && [ "$DATA_TYPES" != "null" ]; then
      ARGS="$ARGS --data-types $DATA_TYPES"
    fi
    echo "[$(date -Iseconds)] Backfill done. Switching to routine sync."
  fi

  echo "[$(date -Iseconds)] Sync done. Sleeping ${INTERVAL} min..."
  sleep $((INTERVAL * 60))
done
