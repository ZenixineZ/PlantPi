# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlantPi is a Raspberry Pi-based automatic plant watering system. It reads soil moisture and light levels via an ADS1115 ADC over I2C, controls a water pump via a GPIO relay, logs sensor data to CSV, sends email alerts, and exposes a REST API for remote control.

## Running the Application

```bash
# Normal run (prompts for plant profile selection)
python3 PlantPi.py

# Common flags
python3 PlantPi.py --simulator          # Simulate with all-zero sensor data (off-Pi dev)
python3 PlantPi.py --simulator sample_simu.csv  # Simulate with CSV data
python3 PlantPi.py -v                   # Verbose: print sensor readings each cycle
python3 PlantPi.py -t                   # Test mode: sample every 0.5s instead of 30 min
python3 PlantPi.py -w                   # Start with pump continuously on
python3 PlantPi.py -q                   # Quiet: disable email notifications
python3 PlantPi.py -p dracaena          # Select plant profile by name/filename/number
python3 PlantPi.py -f /path/to/data.csv # Specify output CSV path
```

**Key runtime controls** (keyboard, when not in `-v -t` mode):
- `s` — take an immediate sample
- `w` (hold) — manually water
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
- **`profiles/*.json`** — Plant profiles with moisture/light thresholds
- **`email_auth.json`** — Email credentials (not committed; see `email_auth_sample.json`)
- **`sample_simu.csv`** — Sample simulator input file showing the format

### Key Classes (`PlantPi.py`)
- **`PlantPi`** — Main controller. Owns the ADC, pump GPIO, watering state machine, CSV logging, email alerting, REST endpoints, and a keyboard listener thread.
- **`PlantProfile`** — Data class: `name`, `moisture_min/max` (0–10 scale), `light_min/max`.
- **`ChannelSpec`** — Maps ADC channels to sensor roles (top moisture, bottom moisture, light1, light2).
- **`FakePump`** — Drop-in pump stub used in `--simulator` mode.
- **`RestServer`** — Flask server thread; endpoints added via `add_endpoint()`.

### Moisture Mapping
Raw ADC values (0–1 normalized, 0.283 = wet, 0.428 = dry) are linearly mapped to a 1.5–10 scale via `map_moisture()`. The same mapping constants are duplicated in `moisture_plots.py`.

### Watering State Machine (`water_if_thirsty`)
- Safety limits: `max_continuous` (default 30s) and `max_daily` (default 300s) — violations send email alert and raise `RuntimeError`.
- Fill cycle: when bottom sensor is below threshold, water for `fill_time` seconds, pause for `2×fill_time`, repeat until threshold met or `fill_pad` fraction reached.
- Top-off: when only the top sensor is dry (and bottom isn't over-saturated), water continuously until top threshold is met.

### REST API (port 8080)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/data`  | Full CSV history (up to ~100 MB), with optional `start_time`/`end_time` JSON body |
| GET    | `/sample`| Current sensor reading snapshot |
| POST   | `/water` | Toggle pump or water for `{"time": N}` seconds |
| POST   | `/plant` | Switch plant profile by name or inline JSON spec |

### Configuration Files
**`email_auth.json`** — copy from `email_auth_sample.json`:
```json
{"user": "...", "password": "...", "to": "...", "from": "..."}
```

**`profiles/<name>.json`** — plant profile format:
```json
{"name": "Dragon Plant (Dracaena)", "moisture_min": 3, "moisture_max": 7, "light_min": 4, "light_max": 7}
```
Moisture and light values are on a 0–10 scale. Profiles are loaded at startup from `profiles/`.

### Simulator CSV Format (`--simulator <file>`)
```
SEQ,TOP,BOTTOM,LIGHT1,LIGHT2
0,0.41,0.35,0.0,0.0
20,0.32,0.35,0.0,0.0
```
SEQ is a sample sequence number; the simulator holds each row's values until the next SEQ is reached.

## Hardware Notes
- ADC: ADS1115 via I2C
- Pump relay: active-low GPIO (default pin 14, must be < 26)
- Logs written to `logs/` with a `latest.log` symlink updated atomically on each run
