# New tables — client reference (v1.2.0 + v1.3.0)

Reference for consumers querying the database. Everything lives in the same
PostgreSQL database. New tables are created automatically on the next sync
(`create_tables()` → `Base.metadata.create_all`).

## Common conventions

- **Keys:** every table is per user. Daily tables use PK `(user_id, calendar_date)`;
  `nap` uses `(user_id, start_ts)`; `gear` uses `(user_id, uuid)`.
- **Upsert, not history:** one row per key, updated in place each sync. No `latest`
  flag on these tables (unlike `personal_record` / `race_predictions` / `user_profile`).
  `update_ts` = last update, `create_ts` = row creation.
- **`raw` (json) column = source of truth:** all v1.3.0 tables store the full Garmin
  payload in `raw`. The typed columns are a convenience (best-effort extraction);
  any field not promoted to a typed column is still available in `raw`. Query with
  PostgreSQL JSON operators: `raw ->> 'field'`, nested `raw -> 'obj' ->> 'field'`.
- **Units:** distance in meters, duration in seconds, hydration in mL, calories in
  kcal. `calendar_date` is a plain date; `nap.start_ts` / `nap.end_ts` are
  `timestamptz` (UTC).
- **Data availability:** rows exist only for days Garmin actually recorded data.
- ⚠️ **`nap` is experimental:** the `dailyEvents` payload shape has not been verified
  against live data yet. Typed columns may be NULL / rows may be missing until
  confirmed — but `nap.raw` preserves the full event and source files are archived.
  Verify against a real payload before relying on the typed nap fields.

## Type mapping (SQLAlchemy → PostgreSQL)

`BigInteger`→bigint, `Integer`→integer, `Float`→double precision,
`String`/`Text`→varchar/text, `Date`→date, `DateTime(timezone=True)`→timestamptz,
`DateTime`→timestamp, `JSON`→json, `Boolean`→boolean.

---

## Tables

Each table below lists its source Garmin endpoint (the pipeline data-type name in
parentheses).

### `nap` — individual naps (v1.3.0)
Source: `/wellness-service/wellness/dailyEvents?calendarDate=` (`DAILY_EVENTS`)

| column | type | note |
|---|---|---|
| user_id | bigint | PK, FK `user.user_id` |
| start_ts | timestamptz | PK |
| end_ts | timestamptz | |
| calendar_date | date | |
| duration_seconds | integer | |
| event_type | varchar | |
| activity_type | varchar | |
| raw | json | full source event |
| create_ts, update_ts | timestamp | |

### `daily_summary` — all-day dashboard rollup (v1.3.0)
Source: `/usersummary-service/usersummary/daily/{display_name}?calendarDate=` (`DAILY_SUMMARY`)
PK `(user_id, calendar_date)`

| column | type |
|---|---|
| total_kilocalories, active_kilocalories, bmr_kilocalories, wellness_kilocalories | double precision |
| total_steps, daily_step_goal | integer |
| total_distance_meters | double precision |
| highly_active_seconds, active_seconds, sedentary_seconds, sleeping_seconds | integer |
| floors_ascended, floors_descended | double precision |
| floors_ascended_goal | integer |
| min_heart_rate, max_heart_rate, resting_heart_rate | integer |
| average_stress_level, max_stress_level | integer |
| body_battery_highest, body_battery_lowest | integer |
| moderate_intensity_minutes, vigorous_intensity_minutes | integer |
| raw | json |
| create_ts, update_ts | timestamp |

### `hrv_daily` — all-day HRV summary (v1.3.0)
Source: `/hrv-service/hrv/{date}` (`HRV`) — distinct from the sleep-window HRV in the Sleep dataset.
PK `(user_id, calendar_date)`

`weekly_avg, last_night_avg, last_night_5min_high` (integer); `status` (varchar);
`baseline_low_upper, baseline_balanced_low, baseline_balanced_upper` (integer);
`baseline_marker_value` (double precision); `raw` (json); `create_ts, update_ts`.

### `resting_hr` — daily resting heart rate (v1.3.0)
Source: `/userstats-service/wellness/daily/{display_name}?...&metricId=60` (`RESTING_HR`)
PK `(user_id, calendar_date)`

`resting_hr` (integer); `raw` (json); `create_ts, update_ts`.

### `spo2_daily` — all-day pulse oximetry (v1.3.0)
Source: `/wellness-service/wellness/daily/spo2/{date}` (`SPO2_DAILY`) — distinct from sleep-window SpO2.
PK `(user_id, calendar_date)`

`average_spo2, lowest_spo2, latest_spo2` (integer); `raw` (json); `create_ts, update_ts`.

### `max_metrics` — VO2 max / MET (v1.3.0)
Source: `/metrics-service/metrics/maxmet/daily/{date}/{date}` (`MAX_METRICS`)
PK `(user_id, calendar_date)`

`vo2_max_running, vo2_max_cycling, fitness_age` (double precision); `raw` (json); `create_ts, update_ts`.

### `fitness_age` (v1.3.0)
Source: `/fitnessage-service/fitnessage/{date}` (`FITNESS_AGE`)
PK `(user_id, calendar_date)`

`fitness_age, achievable_fitness_age` (double precision); `raw` (json); `create_ts, update_ts`.

### `hydration` — daily fluid intake (v1.3.0)
Source: `/usersummary-service/usersummary/hydration/daily/{date}` (`HYDRATION`)
PK `(user_id, calendar_date)`

`value_ml, goal_ml, daily_average_ml, sweat_loss_ml` (double precision); `raw` (json); `create_ts, update_ts`.

### `lifestyle_log` — daily lifestyle logging (v1.3.0)
Source: `/lifestylelogging-service/dailyLog/{date}` (`LIFESTYLE_LOGGING`)
PK `(user_id, calendar_date)`

Only `raw` (json) — structure varies; `create_ts, update_ts`.

### `gear` — registered equipment (v1.2.0)
Source: `/gear-service/gear/filterGear?userProfilePk=` (`GEAR`)
PK `(user_id, uuid)`

`gear_pk` (bigint); `gear_make_name, gear_model_name, custom_make_model,
gear_type_name, gear_status_name, display_name` (varchar); `maximum_meters`
(double precision); `date_begin, date_end, create_date, update_date` (timestamp);
`create_ts, update_ts`. (No `raw` column.)

---

## Example queries

```sql
-- Naps in the last 30 days
SELECT calendar_date, start_ts, end_ts, duration_seconds
FROM nap
WHERE user_id = :uid AND start_ts >= now() - interval '30 days'
ORDER BY start_ts DESC;

-- Daily rollup: calories and activity time
SELECT calendar_date, total_kilocalories, active_kilocalories,
       total_steps, resting_heart_rate, body_battery_highest, body_battery_lowest
FROM daily_summary
WHERE user_id = :uid AND calendar_date BETWEEN :from AND :to
ORDER BY calendar_date;

-- HRV trend plus a non-typed field pulled from raw
SELECT calendar_date, weekly_avg, last_night_avg, status,
       raw -> 'hrvSummary' ->> 'lastNightAvg' AS raw_last_night
FROM hrv_daily
WHERE user_id = :uid ORDER BY calendar_date DESC;

-- Active (non-retired) gear
SELECT display_name, gear_type_name, custom_make_model, maximum_meters
FROM gear
WHERE user_id = :uid
  AND (gear_status_name IS NULL OR gear_status_name <> 'retired');

-- Combine resting HR + HRV + SpO2 per day
SELECT ds.calendar_date, ds.resting_heart_rate,
       h.weekly_avg AS hrv_weekly, sp.average_spo2
FROM daily_summary ds
LEFT JOIN hrv_daily  h  ON h.user_id  = ds.user_id AND h.calendar_date  = ds.calendar_date
LEFT JOIN spo2_daily sp ON sp.user_id = ds.user_id AND sp.calendar_date = ds.calendar_date
WHERE ds.user_id = :uid
ORDER BY ds.calendar_date;
```

**Recommendation:** use the typed columns for common fields, but fall back to
`raw ->> '...'` for anything else, and treat `raw` as the source of truth until the
typed nap / HRV / max_metrics fields are verified against real payloads.
