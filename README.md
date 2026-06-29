# Garmin Sync Add-on for Home Assistant

Syncs Garmin Connect health data to PostgreSQL every N minutes. Runs the full ETL pipeline — sleep, heart rate, HRV, stress, body battery, steps, respiration, floors, SpO2, activities, training readiness, and more.

## Installation

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   
   Paste: `https://github.com/smobaraki/garmin-sync-addon`

2. Install the "Garmin Sync" add-on.

3. Fill in configuration under the **Configuration** tab:
   - `garmin_email` / `garmin_password` — Garmin Connect credentials
   - `garmin_token_json` — **(preferred)** paste the full contents of `garmin_tokens.json` to skip password login
   - `database_url` — PostgreSQL connection string
   - `sync_interval_min` — minutes between syncs (default 30)

4. Start the add-on. It will sync immediately and then every N minutes.

## Token persistence

Refreshed OAuth tokens are stored in `/data/.garminconnect/` and survive add-on restarts and updates.

## Supported architectures

- `aarch64` (Raspberry Pi 4/5, Home Assistant Yellow/Green)
- `amd64` (x86 PCs, VMs)
- `armv7` (Raspberry Pi 3)
