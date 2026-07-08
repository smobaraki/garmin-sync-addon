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
SYNC_SEC=$(jq -r '.sync_interval_sec // empty' "$OPTIONS")
BACKFILL_START=$(jq -r '.backfill_start // empty' "$OPTIONS")
DATA_TYPES=$(jq -r '.data_types // empty' "$OPTIONS")

# Resolve the sleep interval in seconds. sync_interval_sec (when set) wins over
# the minute-based sync_interval_min. A hard 60s floor is enforced here as a
# safety net, independent of the Home Assistant schema validation.
if [ -n "$SYNC_SEC" ] && [ "$SYNC_SEC" != "null" ]; then
  SLEEP_SECONDS="$SYNC_SEC"
else
  SLEEP_SECONDS=$((INTERVAL * 60))
fi
if [ "$SLEEP_SECONDS" -lt 60 ]; then
  SLEEP_SECONDS=60
fi

TOKEN_JSON=$(jq -r '.garmin_token_json // empty' "$OPTIONS")
if [ -n "$TOKEN_JSON" ] && [ "$TOKEN_JSON" != "null" ]; then
  export GARMIN_TOKEN_JSON="$TOKEN_JSON"
fi

export GARMIN_TOKEN_DIR=/data/.garminconnect
mkdir -p "$GARMIN_TOKEN_DIR"

# Build the routine args for a given day. Recomputed every loop iteration so
# a long-running container always syncs the *actual* current day (including
# today's still-incomplete data) instead of a date frozen at startup.
build_routine_args() {
  local day="$1"
  local args="--start-date $day --end-date $day"
  if [ -n "$DATA_TYPES" ] && [ "$DATA_TYPES" != "null" ]; then
    args="$args --data-types $DATA_TYPES"
  fi
  echo "$args"
}

# Decide whether a one-time backfill run is still pending.
PENDING_BACKFILL=0
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
        PENDING_BACKFILL=1
        echo "=== Backfill — $BACKFILL_START → today (then routine) ==="
      else
        echo "=== Backfill $BACKFILL_START already done — routine mode ==="
      fi
    else
      echo "=== Backfill mode but no start date — routine mode ==="
    fi
    ;;
  *)
    echo "=== Routine mode — syncing current day ==="
    ;;
esac

echo "Interval: ${SLEEP_SECONDS}s"
echo "DB: ${DATABASE_URL%%@*}@***"
echo ""

while true; do
  TODAY=$(date +%Y-%m-%d)

  if [ "$PENDING_BACKFILL" = "1" ]; then
    ARGS="--start-date $BACKFILL_START --end-date $TODAY"
    if [ -n "$DATA_TYPES" ] && [ "$DATA_TYPES" != "null" ]; then
      ARGS="$ARGS --data-types $DATA_TYPES"
    fi
  else
    ARGS=$(build_routine_args "$TODAY")
  fi

  echo "[$(date -Iseconds)] Running ETL..."
  python -m garmin_health_data.cli extract $ARGS
  touch "$STATE_FILE"

  if [ "$PENDING_BACKFILL" = "1" ]; then
    touch "${BF_FILE:-/data/.garmin_backfill_done}"
    PENDING_BACKFILL=0
    echo "[$(date -Iseconds)] Backfill done. Switching to routine sync."
  fi

  echo "[$(date -Iseconds)] Sync done. Sleeping ${SLEEP_SECONDS}s..."
  sleep "$SLEEP_SECONDS"
done
