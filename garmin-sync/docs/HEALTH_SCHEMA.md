# Health schema — quick‑start

Schema-et er allerede opprettet mot `garmin_sync` og eies av `garmin_user`.
Både addon-prosessen og klienten bruker samme rolle → full skrivetilgang.

## Kjøre skjemaet (første gang eller ved oppdateringer)

```bash
# Fra repo-roten eller via HA-terminal (psql tilgjengelig)
psql "postgresql://garmin_user:PASSORD@localhost:5432/garmin_sync" \
     -f garmin-sync/docs/health_schema.sql
```

SQL-en bruker `IF NOT EXISTS` / `CREATE OR REPLACE` — trygt å kjøre på nytt.

---

## Tabell-oversikt

| Tabell | Nøkkel | Beskrivelse |
|---|---|---|
| `manufacturer` | `manufacturer_id` | Produsent (f.eks. Solaray, Möllers) |
| `supplement` | `supplement_id` | Katalog over alle vitaminer/medikamenter du eier |
| `supplement_ingredient` | `ingredient_id` | Næringsinnhold per produkt (per porsjon) |
| `inventory` | `inventory_id` | Lagerbeholdning, utløpsdato, lavt-lager-varsel |
| `schedule` | `schedule_id` | Plan: hvilke supplementer, dosering, frekvens |
| `schedule_time` | `schedule_time_id` | Tidspunkt(er) per dag (støtter morgen/kveld) |
| `intake_log` | `intake_id` | Om du tok dosen eller ikke |

### View
- **`daily_vitamins`** — dagens plan + inntaksstatus (ferdig joinet av `schedule` × `supplement` × `intake_log`).

---

## Eksempler

### 1. Registrere en produsent
```sql
INSERT INTO health.manufacturer (name, country) VALUES ('Solaray', 'US');
```

### 2. Registrere et vitamin med ingredienser
```sql
INSERT INTO health.supplement (name, brand_name, category, form, strength_amount, strength_unit, servings_per_container)
VALUES ('D3 + K2', 'Solaray', 'vitamin', 'softgel', 62.5, 'mcg', 60);

INSERT INTO health.supplement_ingredient (supplement_id, nutrient, amount, unit, percent_daily_value)
VALUES (1, 'D3 (cholecalciferol)', 62.5, 'mcg', 312),
       (1, 'K2 (menaquinone-7)', 100, 'mcg', 133);
```

### 3. Sette opp en daglig plan
```sql
-- Enkel: én pille hver dag
INSERT INTO health.schedule (supplement_id, dose_amount) VALUES (1, 1);

-- Med tidspunkt: morgen + kveld
INSERT INTO health.schedule (supplement_id, dose_amount, frequency_type)
VALUES (1, 1, 'times_per_day');
-- tidspunkt-ID-en finner du fra forrige insert:
INSERT INTO health.schedule_time (schedule_id, time_of_day, label) VALUES (2, '08:00', 'Frokost');
INSERT INTO health.schedule_time (schedule_id, time_of_day, label) VALUES (2, '20:00', 'Middag');

-- Annenhver dag
INSERT INTO health.schedule (supplement_id, dose_amount, frequency_type, interval_days)
VALUES (1, 1, 'interval_days', 2);

-- Kun man/ons/fre
INSERT INTO health.schedule (supplement_id, dose_amount, frequency_type, days_of_week)
VALUES (1, 1, 'specific_days', '{0,2,4}');
```

### 4. Logge inntak
```sql
-- Tatt
INSERT INTO health.intake_log (supplement_id, schedule_id, scheduled_date, status, taken_ts, dose_amount_taken)
VALUES (1, 1, current_date, 'taken', now(), 1);

-- Hoppet over (bevisst)
INSERT INTO health.intake_log (supplement_id, schedule_id, scheduled_date, status, notes)
VALUES (1, 1, current_date, 'skipped', 'Glemte');
```

### 5. Lagerbeholdning
```sql
INSERT INTO health.inventory (supplement_id, quantity_remaining, unit, expiry_date, low_stock_threshold)
VALUES (1, 45, 'softgel', '2027-06-30', 10);
```

---

## Nyttige spørringer

### Dagens vitaminer (ferdig join, bruk viewet)
```sql
SELECT * FROM health.daily_vitamins ORDER BY time_of_day NULLS FIRST;
```

### Markere alle dagens doser som tatt (bulk)
```sql
INSERT INTO health.intake_log (supplement_id, schedule_id, scheduled_date, status, taken_ts, dose_amount_taken)
SELECT supplement_id, schedule_id, day, 'taken', now(), dose_amount
FROM health.daily_vitamins
WHERE status = 'pending'
ON CONFLICT (schedule_id, scheduled_ts) DO UPDATE SET status = 'taken', taken_ts = now();
```

### Etterlevelse siste 30 dager
```sql
SELECT s.schedule_id, sup.name,
       COUNT(il.intake_id)            AS doser,
       COUNT(*) FILTER (WHERE il.status='taken')    AS tatt,
       ROUND(100.0 * COUNT(*) FILTER (WHERE il.status='taken') / COUNT(il.intake_id), 1) AS pct
FROM health.schedule s
JOIN health.supplement sup ON sup.supplement_id = s.supplement_id
LEFT JOIN health.intake_log il ON il.schedule_id = s.schedule_id
  AND il.scheduled_date >= current_date - 30
WHERE s.active GROUP BY s.schedule_id, sup.name ORDER BY sup.name;
```

### Hva bør jeg kjøpe? (lavt lager)
```sql
SELECT sup.name, inv.quantity_remaining, inv.unit, inv.expiry_date, inv.low_stock_threshold
FROM health.inventory inv
JOIN health.supplement sup ON sup.supplement_id = inv.supplement_id
WHERE inv.quantity_remaining <= COALESCE(inv.low_stock_threshold, 5) AND inv.expiry_date > current_date
ORDER BY inv.quantity_remaining;
```

### Join mot Garmin-data — søvnkvalitet vs. vitamininntak
```sql
SELECT dv.day, dv.name AS supplement, dv.status,
       ds.total_kilocalories,
       sl.score_overall_value AS sleep_score,
       sl.sleep_score_feedback
FROM health.daily_vitamins dv
LEFT JOIN public.daily_summary ds ON ds.user_id = 125239042 AND ds.calendar_date = dv.day
LEFT JOIN public.sleep sl ON sl.user_id = 125239042 AND sl.calendar_date = dv.day
-- ORDER BY dv.day DESC;
;
```
