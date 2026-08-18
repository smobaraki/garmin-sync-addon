/*
========================================================================================
POSTGRESQL VIEWS FOR GARMIN DATA
========================================================================================
Description: Convenience views that pivot the EAV (entity-attribute-value) activity
             tables into wide, typed columns with canonical names. Garmin emits
             device-specific FIT field names (and developer-field variants), so these
             views also normalize name variants into one column each, letting clients
             query without writing their own name-discovery logic.

             Regular views (not materialized): no extra storage, always fresh, and the
             `activity_id` leading column in each GROUP BY lets the planner push a
             `WHERE activity_id = $1` predicate down to the underlying PK index, so a
             per-activity read only touches that activity's rows.
========================================================================================
*/

---------------------------------------------------------------------------------------
-- v_activity_ts: wide per-record time-series pivot of activity_ts_metric.
-- One row per (activity_id, timestamp) with a column per canonical metric.
---------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_activity_ts AS
SELECT
    activity_id,
    timestamp,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directheartrate','heart_rate','heartrate','sumhr'))::double precision AS heart_rate,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directspeed','speed','sumspeed'))::double precision AS speed,
    MAX(value) FILTER (WHERE LOWER(name) = 'enhanced_speed')::double precision AS enhanced_speed,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directelevation','elevation','altitude','enhanced_altitude','sumaltitude'))::double precision AS altitude,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directdoublecadence','directbikecadence','directswimcadence','directstrokecadence','cadence','runcadence','bikingcadence','sumruncadence','bikecadence'))::double precision AS cadence,
    MAX(value) FILTER (WHERE LOWER(name) IN ('stride_length'))::double precision AS stride_length,
    MAX(value) FILTER (WHERE LOWER(name) IN ('vertical_oscillation'))::double precision AS vertical_oscillation,
    MAX(value) FILTER (WHERE LOWER(name) IN ('vertical_ratio'))::double precision AS vertical_ratio,
    MAX(value) FILTER (WHERE LOWER(name) IN ('stance_time','ground_contact_time'))::double precision AS ground_contact_time,
    MAX(value) FILTER (WHERE LOWER(name) IN ('stance_time_balance','ground_contact_balance'))::double precision AS ground_contact_balance,
    MAX(value) FILTER (WHERE LOWER(name) = 'power')::double precision AS power,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directrespirationrate','respiration_rate','enhanced_respiration_rate','direct_respiration'))::double precision AS respiration_rate,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directpotentialstamina','direct_stamina','potential_stamina'))::double precision AS potential_stamina,
    MAX(value) FILTER (WHERE LOWER(name) IN ('directairtemperature','direct_temperature','temperature'))::double precision AS temperature,
    MAX(value) FILTER (WHERE LOWER(name) = 'activity_type')::double precision AS activity_type,
    MAX(value) FILTER (WHERE LOWER(name) = 'distance')::double precision AS distance,
    MAX(value) FILTER (WHERE LOWER(name) = 'position_lat')::double precision AS position_lat_sc,
    MAX(value) FILTER (WHERE LOWER(name) = 'position_long')::double precision AS position_long_sc
FROM activity_ts_metric
GROUP BY activity_id, timestamp;

---------------------------------------------------------------------------------------
-- v_activity_laps: wide per-lap pivot of activity_lap_metric.
-- One row per (activity_id, lap_idx). Timers are cumulative seconds from activity
-- start (total_elapsed_time includes pauses, total_timer_time does not).
---------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_activity_laps AS
SELECT
    activity_id,
    lap_idx,
    MAX(value) FILTER (WHERE name = 'total_elapsed_time')::double precision AS elapsed_time,
    MAX(value) FILTER (WHERE name = 'total_timer_time')::double precision   AS timer_time,
    MAX(value) FILTER (WHERE name = 'total_distance')::double precision     AS distance,
    MAX(value) FILTER (WHERE name = 'avg_speed')::double precision          AS avg_speed,
    MAX(value) FILTER (WHERE name = 'enhanced_avg_speed')::double precision AS enhanced_avg_speed,
    MAX(value) FILTER (WHERE name = 'avg_power')::double precision          AS avg_power,
    MAX(value) FILTER (WHERE name = 'avg_heart_rate')::double precision     AS avg_heart_rate,
    MAX(value) FILTER (WHERE name = 'avg_cadence')::double precision        AS avg_cadence
FROM activity_lap_metric
GROUP BY activity_id, lap_idx;

---------------------------------------------------------------------------------------
-- v_activity_splits: wide per-split pivot of activity_split_metric.
-- One row per (activity_id, split_idx). `split_type` holds Garmin's run/walk
-- detection labels (e.g. rwd_run, rwd_walk, rwd_stand, interval_active).
---------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_activity_splits AS
SELECT
    activity_id,
    split_idx,
    MAX(split_type) AS split_type,
    MAX(value) FILTER (WHERE name = 'total_elapsed_time')::double precision AS elapsed_time,
    MAX(value) FILTER (WHERE name = 'total_timer_time')::double precision   AS timer_time,
    MAX(value) FILTER (WHERE name = 'total_distance')::double precision     AS distance,
    MAX(value) FILTER (WHERE name = 'avg_speed')::double precision          AS avg_speed,
    MAX(value) FILTER (WHERE name = 'avg_power')::double precision          AS avg_power
FROM activity_split_metric
GROUP BY activity_id, split_idx;
