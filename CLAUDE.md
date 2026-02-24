# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlantPi is a Raspberry Pi-based automatic plant watering system. It reads soil moisture via up to two ADS1115 ADCs over I2C (8 channels total), controls up to 8 water pumps via GPIO relays, logs sensor data to CSV, sends email alerts, and exposes a REST API for remote control. Light sensor support has been stripped out and will be reimplemented separately.

## Running the Application

```bash
# Single plant, top + bottom sensors
python3 PlantPi.py --plant dracaena,0,4,14

# Two plants, top-only and top+bottom
python3 PlantPi.py --plant test,0,,14 --plant dracaena,1,5,15

# Simulate with all-zero sensor data (off-Pi dev)
python3 PlantPi.py --simulator --plant dracaena,0,4,14

# Simulate with CSV data
python3 PlantPi.py --simulator sample_simu.csv --plant dracaena,0,4,14

# Common flags
python3 PlantPi.py ... -v     # Verbose: print sensor readings each cycle
python3 PlantPi.py ... -t     # Test mode: sample every 0.5s instead of 30 min
python3 PlantPi.py ... -w     # Start with all pumps continuously on
python3 PlantPi.py ... -w 0 2 # Water plants at index 0 and 2 only
python3 PlantPi.py ... -q     # Quiet: disable email notifications
python3 PlantPi.py ... -f /path/to/data.csv  # Specify output CSV path
```

**`--plant` format:** `PROFILE,TOP_CHANNEL,BOTTOM_CHANNEL,GPIO`
- `PROFILE` — name of a JSON file in `profiles/` (without extension)
- `TOP_CHANNEL` / `BOTTOM_CHANNEL` — ADC channel 0–7, or empty (e.g. `,`) to omit; at least one required
- `GPIO` — relay GPIO pin number (required)

**Key runtime controls** (keyboard, when not in `-v -t` mode):
- `s` — take an immediate sample
- `w` (hold) — manually water all plants
- `q` — quit

## Pi Setup

```bash
# Remote setup (copies setup.sh to Pi, installs deps, clones repo)
./pi_setup.sh -u <pi-user> -i <pi-ip>

# Local setup (run directly on the Pi)
./pi_setup.sh -l
```

Pi dependencies installed by `pi_setup.sh`: `gpiozero`, `matplotlib`, `Adafruit_ADS1x15`, `flask`, `sshkeyboard`, `werkzeug`.

## Architecture

### Files
- **`PlantPi.py`** — Main entry point and all core logic
- **`RestServer.py`** — Thin wrapper around Flask/Werkzeug that runs as a background thread on port 8080
- **`Emailer.py`** — Simple Gmail SMTP wrapper
- **`moisture_plots.py`** — Standalone matplotlib script for offline analysis of recorded CSV data
- **`pi_setup.sh`** — Bootstraps a fresh Pi (remote or local)
- **`profiles/*.json`** — Plant profiles with moisture thresholds
- **`profiles/soil/*.json`** — Soil profiles with ADC sensor calibration values
- **`email_auth.json`** — Email credentials (not committed; see `email_auth_sample.json`)
- **`sample_simu.csv`** — Sample simulator input file showing the format

### Key Classes (`PlantPi.py`)
- **`PlantPi`** — Main controller. Owns the ADC list, plant controllers, CSV logging, email alerting, REST endpoints, and keyboard listener thread.
- **`PlantController`** — Per-plant state and watering logic: moisture readings, pump, fill/top-off state machine, safety limits.
- **`PlantProfile`** — Data class: `name`, `moisture_min/max` (0–10 scale).
- **`SoilProfile`** — Calibration: `dry_sensor`/`wet_sensor` (raw ADC, 0–1 normalized) and `dry_std`/`wet_std` (0–10 output scale). Derives a linear mapping `y = mx + b`.
- **`FakePump`** — Drop-in pump stub used in `--simulator` mode.
- **`RestServer`** — Flask server thread; endpoints added via `add_endpoint()`.

### ADC Channel Routing
Two ADS1115s at I2C addresses 0x48 (channels 0–3) and 0x49 (channels 4–7):
```
channel // 4  → which ADC (0 or 1)
channel % 4   → which input on that ADC
```

### Moisture Mapping
Raw ADC values (0–1 normalized) are mapped to a 0–10 scale via `SoilProfile.map_moisture()`. Default calibration: `dry_sensor=0.428`, `wet_sensor=0.283`, `dry_std=1.5`, `wet_std=10`. Soil profiles can be customized per plant via `--soil-profiles` and loaded from `profiles/soil/<name>.json`.

### Watering State Machine (`PlantController.water_if_thirsty`)
- Safety limits: `max_continuous` (default 30s) and `max_daily` (default 300s) — violations send email alert and raise `RuntimeError`.
- Fill cycle (bottom sensor): water for `fill_time` seconds, pause for `2×fill_time`, repeat until threshold met or `fill_pad` fraction reached.
- Top-off (top sensor only, when bottom is satisfied): water continuously until top threshold is met.
- Plants with only one sensor use fill cycle logic only.

### REST API (port 8080)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/data`  | Full CSV history with optional `start_time`/`end_time` JSON body |
| GET    | `/sample`| Array of per-plant sensor snapshots |
| POST   | `/water` | Toggle pump: optional `{"plant": N}` to target one plant; omit for all |
| POST   | `/plant` | Update plant profile: `{"plant": N, ...profile fields...}` |

### CSV Output
Dynamic header based on configured sensors per plant:
```
TIME,PLANT_0_TOP,PLANT_0_MAPPED_TOP,PLANT_0_BOTTOM,PLANT_0_MAPPED_BOTTOM,PLANT_0_PUMP,...
```
Bottom columns are omitted for plants with no bottom sensor.

### Simulator CSV Format (`--simulator <file>`)
```
TIME,CH0,CH1,CH2,CH3,CH4,CH5,CH6,CH7
0,0.41,0.41,0.0,0.0,0.35,0.35,0.0,0.0
10,0.32,0.32,0.0,0.0,0.35,0.35,0.0,0.0
```
`TIME` is seconds from session start (floats allowed). Each row's values take effect when elapsed time reaches that offset and remain active until the next row fires. Multiple rows can fire in one loop iteration if the loop was slow. Channels not used by any `--plant` spec can be left at 0.

### Configuration Files
**`email_auth.json`** — copy from `email_auth_sample.json`:
```json
{"user": "...", "password": "...", "to": "...", "from": "..."}
```

**`profiles/<name>.json`** — plant profile:
```json
{"name": "Dragon Plant (Dracaena)", "moisture_min": 3, "moisture_max": 7}
```

**`profiles/soil/<name>.json`** — soil profile (all fields optional, fall back to defaults):
```json
{"dry_sensor": 0.428, "wet_sensor": 0.283, "dry_std": 1.5, "wet_std": 10}
```

## Hardware Notes
- ADC: Two ADS1115 at I2C 0x48 and 0x49 (channels 0–3 and 4–7)
- Pump relays: active-low GPIO, specified per plant via `--plant`
- Logs written to `logs/` with a `latest.log` symlink updated atomically on each run
