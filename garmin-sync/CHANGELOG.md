# Changelog

## 1.5.10

- Feature: scrape the remaining Garmin Connect endpoints for a full data mirror:
  per-activity weather, split summaries and gear links; daily endurance score,
  hill score and nutrition food log; range-based calories, weigh-ins, blood
  pressure and running tolerance; and no-date metadata (goals, devices, workouts,
  training plans, pregnancy summary, activity-type catalog, earned badges). All
  new tables carry a `raw` JSON column so no source field is lost.

## 1.5.9

- Feature: scrape the user's configured heart-rate and power zone definitions from
  Garmin's `/biometric-service/heartRateZones` and `/biometric-service/powerZones`
  endpoints into new `heart_rate_zone` and `power_zone` tables (one row per
  `(user_id, sport, zone_number)` with low/high bounds and `changeState`; replace
  semantics on re-sync).
- Feature: add convenience views `v_activity_ts`, `v_activity_laps` and
  `v_activity_splits` that pivot the EAV activity tables into typed columns with
  normalized field names. Applied idempotently via `CREATE OR REPLACE VIEW` after
  table creation.

## 1.5.8

- Fix: calendar month was off by one — the `/calendar-service/year/{year}/month/{month}`
  endpoint is 0-based (January = 0), but `get_calendar` passed a 1-based month, so
  the sync fetched the *next* month (empty) instead of the current one. The URL now
  decrements the caller month.
- Feature: MONTH-typed extraction looks ahead `_CALENDAR_LOOKAHEAD_MONTHS` (2) past
  the effective end date, so upcoming months' scheduled workouts are captured even
  though routine syncs only cover "today".
- Fix: normalize calendar `duration` (milliseconds → seconds) and `distance`
  (centimetres → metres) when mapping items into `calendar_event`.

## 1.5.7

- Feature: scrape the Garmin training calendar into a new `calendar_event`
  table. Adds a MONTH-typed `CALENDAR` data type using the
  `/calendar-service/year/{year}/month/{month}` endpoint, plus a
  `CalendarEvent` model and `_process_calendar` processor that upserts planned
  workouts, training-plan sessions, races, and wellness events keyed by
  `(user_id, item_id)`.

## 1.5.6

- Fix: remove incorrect `UNIQUE (user_id, calendar_date)` index on `sleep`
  that caused duplicate-key violations and quarantined sleep files when a user
  had multiple sleep sessions sharing a calendar date (e.g. a nap detected as
  sleep). The canonical unique key is `(user_id, start_ts)`.

## 1.5.5

- Feature: fetch rich per-activity metadata from the single-activity endpoint
  (`/activity-service/activity/{id}`) and enrich Activity rows with stamina
  (`begin/end/min_potential_stamina`), detailed respiration and temperature
  metrics, `recovery_heart_rate`, `max_vertical_speed`, and
  `min_activity_lap_duration`. These fields are absent from the compact
  ``ACTIVITIES_LIST`` response and were previously NULL for all activities.
  New ``ACTIVITY_DETAILS`` PER_ACTIVITY data type + ``_process_activity_details``.

## 1.5.4

- Fix: store previously missing activity summary fields — stamina
  (`begin_potential_stamina`, `end_potential_stamina`, `min_available_stamina`),
  respiration (`min/max/avg_respiration_rate`), temperature (`average/max/min`),
  `recovery_heart_rate`, `max_vertical_speed`, and `min_activity_lap_duration`.
  These lived in Garmin's nested `summaryDTO` and were never flattened into the
  top-level parser, so they ended up in `supplemental_activity_metric` (key-value)
  or were lost entirely. Also removes duplicate extraction from the cycling
  processor. New columns are auto-added via `_add_missing_columns`.

## 1.5.3

- Fix: the routine sync loop no longer dies when a single `extract` run exits
  non-zero (e.g. the lifecycle lock is held by a concurrent manual backfill, or a
  transient API/429 error). The failed cycle is logged and the loop continues,
  instead of `set -e` killing the whole daemon.

## 1.5.2

- Fix: auto-add columns that models gained after their table was first created.
  `create_all` never alters existing tables, so the `nap` enrichment columns
  (`body_battery_impact`, `feedback_type`, `short_feedback`, `average_stress`)
  were missing on existing databases, causing nap inserts to fail and files to
  quarantine. A best-effort additive `ALTER TABLE ... ADD COLUMN` reconciler now
  runs on init for both PostgreSQL and SQLite.

## 1.5.1

- Fix: SQLite `create_tables` now also runs `Base.metadata.create_all`, so tables
  added after `tables.ddl` was last generated (gear, nap, body_battery_event,
  daily_summary, hrv_daily, etc.) are actually created. Previously a SQLite run
  (e.g. `garmin extract` without `DATABASE_URL`) failed to insert into the new
  tables and quarantined the file.

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
