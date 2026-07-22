# Garmin Sync — client quick-start

Koble klienten din direkte til PostgreSQL-databasen (`garmin_sync`) som
denne addon-en populerer. Alle data er i `public`-schemaet (Garmin) +
`health`-schemaet (vitaminer/medikamenter). Én tilkobling, full lese- og
skrivetilgang via `garmin_user`.

## Nye aktivitet-kolonner (v1.5.4+)

`activity`-tabellen har fått 12 nye kolonner med rike data fra Garmins
per-activity-endepunkt. Disse er **NULL** for aktiviteter som ble synket
før v1.5.5 — re-synk for å fylle dem.

| Kolonne | Garmin-kilde | Eksempel |
|---|---|---|
| `begin_potential_stamina` | `summaryDTO.beginPotentialStamina` | 93.0 |
| `end_potential_stamina` | `summaryDTO.endPotentialStamina` | 60.0 |
| `min_available_stamina` | `summaryDTO.minAvailableStamina` | 59.0 |
| `avg_respiration_rate` | `summaryDTO.avgRespirationRate` | 29.2 |
| `max_respiration_rate` | `summaryDTO.maxRespirationRate` | 40.0 |
| `min_respiration_rate` | `summaryDTO.minRespirationRate` | 18.4 |
| `average_temperature` | `summaryDTO.averageTemperature` | 25.0 |
| `max_temperature` | `summaryDTO.maxTemperature` | 36.0 |
| `min_temperature` | `summaryDTO.minTemperature` | 22.0 |
| `recovery_heart_rate` | `summaryDTO.recoveryHeartRate` | 16 |
| `max_vertical_speed` | `summaryDTO.maxVerticalSpeed` | 0.6 |
| `min_activity_lap_duration` | `summaryDTO.minActivityLapDuration` | 7601.4 |

```sql
-- Stamina-trend for gravel-turer
SELECT start_ts, activity_name,
       begin_potential_stamina, end_potential_stamina,
       ROUND(begin_potential_stamina - end_potential_stamina, 1) AS stamina_drop
FROM activity
WHERE begin_potential_stamina IS NOT NULL
ORDER BY start_ts DESC;

-- Snitt-temperatur per aktivitetstype
SELECT activity_type_key, count(*), ROUND(avg(average_temperature), 1) AS avg_temp
FROM activity
WHERE average_temperature IS NOT NULL
GROUP BY activity_type_key ORDER BY avg_temp DESC;
```

## Naps & Body Battery Events (v1.5.0)

| Tabell | Hva | Nøkkel |
|---|---|---|
| `nap` | Enkeltnapper (start/slutt/varighet, BB-impact, feedback) | `(user_id, start_ts)` |
| `body_battery_event` | Alle BB-hendelser (SLEEP/STRESS/NAP/ACTIVITY/RECOVERY) | `(user_id, event_start_ts, event_type)` |

```sql
-- Naps med body battery impact
SELECT calendar_date, start_ts, end_ts,
       ROUND(duration_seconds/60.0, 1) AS minutes,
       short_feedback, body_battery_impact
FROM nap ORDER BY start_ts DESC;

-- Alle hendelser en gitt dag
SELECT event_type, event_start_ts, duration_seconds, body_battery_impact, short_feedback
FROM body_battery_event
WHERE calendar_date = '2026-07-08'
ORDER BY event_start_ts;
```

## Daglige helse-tabeller (v1.3.0)

Hver av disse har PK `(user_id, calendar_date)` og en `raw` JSON-kolonne:

`daily_summary`, `hrv_daily`, `resting_hr`, `spo2_daily`, `max_metrics`,
`fitness_age`, `hydration`, `lifestyle_log`, `daily_events`

Se **[NEW_TABLES.md](docs/NEW_TABLES.md)** for full skjema-referanse og
eksempel-spørringer.

```sql
-- Dagsrollup: alt på ett brett
SELECT * FROM daily_summary
WHERE user_id = 125239042 AND calendar_date = '2026-07-22';

-- HRV-trend siste 30 dager
SELECT calendar_date, weekly_avg, last_night_avg, status
FROM hrv_daily
WHERE user_id = 125239042
ORDER BY calendar_date DESC LIMIT 30;
```

## Enum-label-mapper (v1.4.x)

Garmin returnerer enum-nøkler som `POSITIVE_LONG_AND_DEEP` — du må oversette
dem selv. Vi har en ferdig **norsk** ordbok med 155 nøkler over 14 domener
+ en deterministisk fallback-humanizer:

- **[enum_labels.json](docs/enum_labels.json)** — oppslagsdata
- **[enum_labels.ts](docs/enum_labels.ts)** — `labelFor(domain, key)` + `labelForColumn(column, key)`

```ts
import { labelForColumn } from "./enum_labels";

labelForColumn("sleep.sleep_score_feedback", "POSITIVE_LONG_AND_DEEP");
// → { label: "Lang og dyp søvn", sentiment: "positive" }

// Fallback — funker selv om nøkkelen ikke er i ordboka:
labelForColumn("body_battery_event.short_feedback", "RESTFUL_NAP");
// → { label: "Avslappende blund", sentiment: "positive" }
```

## Health — vitaminer og medikamenter (v1.5.x)

`health`-schema i samme database, eid av `garmin_user` → full skrivetilgang
for både addon og klient. Se **[HEALTH_SCHEMA.md](docs/HEALTH_SCHEMA.md)**
for kjørekommando, skjema og eksempler.

```sql
-- Dagens vitaminer med status (ferdig joinet)
SELECT * FROM health.daily_vitamins ORDER BY time_of_day;

-- Registrere inntak
INSERT INTO health.intake_log (supplement_id, schedule_id, scheduled_date, status, taken_ts, dose_amount_taken)
VALUES (1, 1, current_date, 'taken', now(), 1);
```

## Gear — utstyr (v1.2.0)

```sql
SELECT display_name, gear_type_name, gear_make_name, gear_model_name, maximum_meters
FROM gear WHERE user_id = 125239042;
```

## Nyttige joins

```sql
-- Søvnkvalitet vs. aktivitetstemperatur
SELECT a.start_ts, a.activity_name, a.average_temperature,
       s.score_overall_value AS sleep_score, s.sleep_score_feedback
FROM activity a
LEFT JOIN sleep s ON s.user_id = a.user_id AND s.calendar_date = a.start_ts::date
WHERE a.user_id = 125239042 AND a.average_temperature IS NOT NULL
ORDER BY a.start_ts DESC LIMIT 10;

-- HRV + hvilepuls + søvnscore per dag
SELECT ds.calendar_date, ds.resting_heart_rate,
       h.weekly_avg AS hrv_weekly, sp.average_spo2
FROM daily_summary ds
LEFT JOIN hrv_daily  h  ON h.user_id = ds.user_id AND h.calendar_date = ds.calendar_date
LEFT JOIN spo2_daily sp ON sp.user_id = ds.user_id AND sp.calendar_date = ds.calendar_date
WHERE ds.user_id = 125239042
ORDER BY ds.calendar_date DESC LIMIT 30;
```

---

**Flere spørsmål?** Se de fullstendige skjema-referansene i `docs/`:
- `docs/NEW_TABLES.md` — alle Garmin-tabeller
- `docs/HEALTH_SCHEMA.md` — vitamin/medikament-tabeller
- `docs/enum_labels.json` / `docs/enum_labels.ts` — norsk enum-ordbok
