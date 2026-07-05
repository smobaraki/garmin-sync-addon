# Changelog

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
