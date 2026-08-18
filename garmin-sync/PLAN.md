# Plan: Scrape alt fra Garmin Connect

Mål: hente ut så mye som mulig fra Garmin Connect API-et og lagre i riktig format —
tidsserier som tidsserier, aggregater som aggregater, metadata som metadata.

## Lagringsformat (taxonomi)

| Datatype | Eksempel | DB-format |
|---|---|---|
| Regelmessig tidsserie | puls, stress, body battery, HRV, SpO2, respirasjon | EAV `(user_id, timestamp, value)` + evt. downsample |
| Per-dag aggregat | dagssum, RHR, max-metrikk | `(user_id, calendar_date)` PK + `raw` JSON |
| Per-aktivitet skalar | distance, tempo, sonetid, stamina | `activity`-kolonner / `supplemental_activity_metric` |
| Per-aktivitet tidsserie | FIT record-frames | `activity_ts_metric` |
| Per-aktivitet sub-liste | splits, laps, vær, øvelser | barnetabeller `(activity_id, …)` |
| Metadata (no-date) | profil, gear, soner, mål, enheter | `(user_id, …)` |

Prinsipp: alle tabeller med kilde-payload får en `raw JSONB`-kolonne slik at ingenting
tapes, selv om et felt ikke er modellert som egen kolonne.

## Gap-katalog

### A. Per-aktivitet sub-data (PER_ACTIVITY) — mangler
- A1 `/activity-service/activity/{id}/weather` → `activity_weather` (temp, luftfukt, vind)
- A2 `/activity-service/activity/{id}/split_summaries` → `activity_split_summary`
- A3 `/activity/{id}/hrTimeInZones` → verifiser mot `summaryDTO` (finnes)
- A4 `/activity/{id}/powerTimeInZones` → verifiser (finnes)
- A5 `get_activity_gear` → `activity_gear` (aktivitet↔gear-kobling)
- A6 `/activity/{id}/splits` (JSON) → gjenbruk `activity_split_metric` (aktivitet uten FIT)
- A7 `get_last_activity` / `get_activities_fordate` → dekket av ACTIVITIES_LIST

### B. Daglig velvære (DAILY/RANGE)
- B1 `get_calories_daily` → `calories_daily` (aggregat)
- B2 `get_weigh_ins` / `get_daily_weigh_ins` → `weigh_in` (tidsserie)
- B3 `/bloodpressure-service/bloodpressure/range` → `blood_pressure` (tidsserie)
- B4 `get_morning_training_readiness` → `morning_readiness` (aggregat)
- B5 `get_weekly_steps` / `get_weekly_stress` → `weekly_*` (aggregat)
- B6 `/biometric-service/biometric` + `/stats` → `biometric` (aggregat)

### C. Ytelsesinnsikt
- C1 `/metrics-service/metrics/endurancescore` + `/stats` → `endurance_score`
- C2 `/metrics-service/metrics/hillscore` + `/stats` → `hill_score`
- C3 `/metrics-service/metrics/runningtolerance/stats` → `running_tolerance`
- C4 `latestLactateThreshold`, `powerToWeight/latest` → berik `user_profile`

### D. Metadata (NO_DATE)
- D1 `/goal-service/goal/goals` → `goal`
- D2 `/device-service/deviceregistration/devices` → `device`
- D3 `/workout-service/workouts` + `/workout/{id}` → `workout` + `workout_step`
- D4 `/trainingplan-service/trainingplan` → `training_plan`
- D5 `/nutrition-service/food/logs`, `/meals`, `/settings` → `nutrition_log`, `nutrition_meal`
- D6 `/periodichealth-service/.../pregnancysnapshot` → `pregnancy_summary`
- D7 `/activity-service/activity/activityTypes` → `activity_type_ref` (statisk)

### E. Data-tap-fiks
- E1 `activity`/`sleep` mangler `raw` JSON → lagt til (ferdig i Fase 1)
- E2 `splitSummaries`, `personalRecords`, `deviceName`, `courseName` osv. droppes →
  bevart i `raw` (ferdig i Fase 1)
- E3 `get_power_zones_for_sport` → utvid POWER_ZONES med sport-parameter

## Faser

### Fase 0 — Utforskning
- GraphQL-gateway-introspeksjon (`query_garmin_graphql`) for endepunkter utenfor REST-biblioteket.
- Nettverksfange Garmin Connect web (devtools) for udokumenterte kall.
- Tørr-kjøre hvert gap-endepunkt, dumpe JSON og fastsette eksakt feltfasong.

### Fase 1 — Data-tap-fiks (UTFØRT)
- `raw JSON` på `activity` (+ `raw_details` for DETAILS-payload) og `sleep`.
- `_process_single_activity` / `_process_sleep` snapshotter payload før pop, lagrer verbatim.

### Fase 2 — Per-aktivitet: A1 (vær), A2 (split summaries), A5 (gear-kobling).

### Fase 3 — Daglig velvære: B1–B6.

### Fase 4 — Ytelse: C1–C4.

### Fase 5 — Metadata: D1–D6.

### Fase 6 — Nice-to-have: badges/challenges, golf, solar, D7.

## Implementasjonsmønster (per datatype)

1. `GarminDataType` i `constants.py` (DAILY/RANGE/NO_DATE/PER_ACTIVITY).
2. `get_*` i `garmin_client/api.py` + wrapper i `client.py`.
3. Modell i `models.py` (eller `create_all` fallback for nye tabeller).
4. `_process_*` i `processor.py` + registrering i `file_processors`.
5. Tidsserier: EAV + downsample; aggregater: `raw` JSON + modellerte kolonner.
