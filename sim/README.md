# Simulation runbook — ArduPilot SITL + Mission Planner spectating + pymavlink mission

Everything runs from a terminal on the Mac. Mission Planner in the Parallels Windows VM is the
spectator / safety-pilot view; the mission code talks to SITL on its own port, exactly like the Pi
talks to the Cube through the MAVProxy bridge on the aircraft.

```
 ┌─────────────────────────────┐   tcp 5762 (SERIAL1)   ┌────────────────────────────┐
 │ ArduCopter SITL (hexa)      │◄──────────────────────►│ imav-m1 run --profile sim   │ terminal 3
 │ scripts/start_sitl.sh       │                        │ state machine + dashboard   │ http://localhost:5000
 │ home = Haguenau (§5.2)      │   tcp 5760 (SERIAL0)   └────────────────────────────┘
 │                             │◄──────────────────────►  MAVProxy bridge ──udp 14550──► Mission Planner (VM)
 └─────────────────────────────┘   tcp 5763 (SERIAL2)     scripts/mavproxy_gcs_bridge.sh      terminal 2
```

## 0. One-time
- A built SITL binary exists at
  `~/Desktop/MSc Aerial Robotics/Group Project Assignment/SITL/ardupilot/build/sitl/bin/arducopter`
  (ArduCopter 4.6.0-beta1). The scripts use it by default; set `ARDUPILOT_DIR` to use another checkout.
- `make setup` (or `.venv/bin/pip install -e ".[dev]"`) once, so `.venv/bin/imav-m1` exists.
- `mavproxy.py` is already installed in the pyenv Python 3.10 (`which mavproxy.py`).

> Do **not** use `sim_vehicle.py` here: on macOS it opens the vehicle in a new Terminal window and
> the headless runs never see it. `scripts/start_sitl.sh` runs the binary directly.

## 1. Terminal 1 — start SITL (headless)
```bash
scripts/start_sitl.sh --fg         # foreground: SITL log in this terminal, Ctrl-C to stop (recommended)
scripts/start_sitl.sh              # or background: log in sim/runtime/sitl.log, scripts/stop_sitl.sh to stop
```
Options: `SPEEDUP=5 scripts/start_sitl.sh` (faster than real time), `WIPE=1 …` (reset params/eeprom),
`FRAME=quad …`. Stop with `scripts/stop_sitl.sh`. Give it ~30 s after start for GPS + EKF to settle
before arming (the preflight page shows the checks going green).

## 2. Terminal 2 — Mission Planner in the Parallels VM (spectate)
Option A (proven on the SaR project): MAVProxy bridge → UDP into the VM.
```bash
scripts/mavproxy_gcs_bridge.sh ROBINCARTER17AB.local     # or the VM's IP (ipconfig in Windows)
```
In Mission Planner: connection type **UDP**, port **14550**, Connect. (Same as flying days: the Pi's
MAVProxy pushed `udp:ROBINCARTER17AB.local:14550`.)

Option B (no MAVProxy): connection type **TCP**, host = the Mac as seen from the VM
(`ifconfig vnic0` on the Mac, usually `10.211.55.2` with Parallels shared networking), port **5763**.

Mission Planner shows the aircraft, the uploaded fence and mission (Plan tab → "Read WPs" after the
upload if it does not refresh), and you can take over from it exactly like a safety pilot would
(switch to LOITER → the state machine pauses; back to GUIDED → it resumes; RTL/LAND → it aborts).

## 3. Terminal 3 — run the pymavlink mission
Interactive (operator dashboard at http://localhost:5000, buttons 1 → 2 → 3):
```bash
.venv/bin/imav-m1 run --profile sim
```
Fully scripted (no clicking; exits when the results are written):
```bash
.venv/bin/imav-m1 run --profile sim --auto --no-gui
```
Useful flags: `--kml path/to/areas.kml` (placemarks "Mapping Area 1", "Flight Area", "Landing"),
`--detector none` (no placeholder detections), `--name smoke` (run folder suffix), `--port 5001`.

Outputs land in `data/flights/YYYY-MM-DD_sim_NN_<name>/`: `run.yaml`, `telemetry.jsonl`,
`detections/`, `results/` (vehicle table CSV, map SVG, summary JSON) and `results.zip`.

Plan only (no vehicle) — preview SVG + timings for the configured area:
```bash
.venv/bin/imav-m1 plan --profile sim
```

## 4. Make shortcuts
```
make sitl / make sitl-stop        start / stop SITL
make gcs-bridge GCS=<host-or-ip>  MAVProxy → Mission Planner (UDP 14550)
make mission-sim                  dashboard run          make mission-sim-auto   scripted run
make plan-sim                     offline plan preview
```

## 5. What the test area is
`config/sim.yaml` carries a 440 × 280 m rectangle (Mapping Area 1 size) centred on the rulebook site
fence and three synthetic "vehicles" for the placeholder detector; the fence is the §5.2 site geofence
because no flight-area polygon is known yet. Replace with `--kml` on the day.

## 6. Fault scenarios (SIM_TO_REAL stage 2) — from a MAVProxy console on port 5760
```
param set SIM_GPS_DISABLE 1        # GPS loss     → EKF failsafe
param set SIM_BATT_VOLTAGE 10.0    # low battery → battery failsafe
mode LOITER / mode GUIDED / mode RTL   # pilot override / hand-back / failsafe-like
```
The state machine must never fight these: watch the dashboard go PAUSED / ABORT and the log.
