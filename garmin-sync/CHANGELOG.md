# Changelog

## 1.5.0

- Fix: naps are now correctly sourced from the **body battery events** endpoint
  (`/wellness-service/wellness/bodyBattery/events`), where `event.eventType == "NAP"`.
  The previous `dailyEvents` source never contained naps.
- New `BODY_BATTERY_EVENTS` data type and `body_battery_event` table: one row per
  event (sleep, stress, nap, activity) with start time, duration, body-battery
  impact, feedback, and average stress.
- `nap` table enriched with `body_battery_impact`, `feedback_type`, `short_feedback`,
  `average_stress`, and now populated with real start/end/duration.
- `DAILY_EVENTS` now only stores auto-detected activities (raw), no longer used for naps.

## 1.4.1

- Fix/diagnostic: `DAILY_EVENTS` now always stores the full raw payload in a new
  `daily_events` table (one row per day), in addition to best-effort nap
  extraction. This makes it possible to verify/refine the nap parser against real
  data and ensures the events payload is never lost when the nap parser does not
  recognise an event shape.

## 1.4.0

- Feature: sync interval can now be set in **seconds** via `sync_interval_sec`
  (floor 60s, default 90s), which overrides the minute-based `sync_interval_min`.
  Enables sub-5-minute syncing. Note: routine sync re-fetches every data type each
  cycle, so frequent syncing multiplies the Garmin API call volume — watch the log
  for HTTP 429 (rate limiting).

## 1.3.0

- Feature (full-mirror phase 1): fetch and store **naps** and core daily-health
  data so it no longer requires opening Garmin Connect. New DAILY data types and
  tables:
  - `DAILY_EVENTS` → `nap` (individual naps with start/end/duration)
  - `DAILY_SUMMARY` → `daily_summary` (all-day dashboard rollup)
  - `HRV` → `hrv_daily` (all-day HRV + status)
  - `RESTING_HR` → `resting_hr`
  - `SPO2_DAILY` → `spo2_daily`
  - `MAX_METRICS` → `max_metrics`
  - `FITNESS_AGE` → `fitness_age`
  - `HYDRATION` → `hydration`
  - `LIFESTYLE_LOGGING` → `lifestyle_log`
  Each table keeps a `raw` JSON column so nothing from the source payload is lost.
  Tables are created automatically on the next sync.

## 1.2.0

- Feature: fetch and store Garmin **gear** (shoes, bikes, and other equipment).
  Adds a `GEAR` data type, the `/gear-service/gear/filterGear` endpoint, and a new
  `gear` table (make, model, type, status, usage limit, begin/end dates). The table
  is created automatically on the next sync.

## 1.1.3

- Fix: recompute the sync date on every loop iteration so routine mode always
  tracks the actual current day. Previously the date was frozen at container
  startup, so a long-running container kept re-fetching the startup date and
  never synced today's data.

## 1.1.2

- Bump version.

## 1.1.1

- Fix: backfill state keyed by date — re-trigger on date change, no SSH needed.
- Fix: use a separate state file for backfill.

## 1.1.0

- Add mode selector (routine / backfill / auth) and simplify date handling.
- Fix: use `str` schema for the mode field.
- Fix: always pass `--end-date` to prevent inverted date ranges.
