# IMAV 2026 — Outdoor Mission 1: Mapping and Vehicle Identification

Competition: **IMAV 2026, 21–25 September 2026** — outdoor flying at the Haguenau military training ground
(rulebook V4, 1 Sep 2026 — see `docs/rulebook/`).

Goal: fly a fully autonomous mission (Outdoor Mission 1) that maps a 440 × 280 m area, locates up to
eight fire-brigade / military vehicles to within 5 m and identifies them, on an ArduPilot quadrotor with a Raspberry Pi companion computer, developed
**simulation-first** in ArduPilot SITL and transitioned to hardware through a
gated checklist.

## Read these first
| File | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Project context + hard rules for any AI assistant working in this repo |
| [docs/WORKING_NOTES.md](docs/WORKING_NOTES.md) | Scratch thinking, open questions, ideas (messy is fine) |
| [docs/PROGRESS_LOG.md](docs/PROGRESS_LOG.md) | Dated log: what changed, how it was tested, result, next |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Rulebook-traced requirements (R-xx) — the source of truth for "done" |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decision records (why we chose X over Y) |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Airframe, autopilot, companion, camera, wiring, pinned versions |
| [docs/SIM_TO_REAL.md](docs/SIM_TO_REAL.md) | Gate checklist: what must be true before code touches the aircraft |
| [docs/SAFETY.md](docs/SAFETY.md) | Non-negotiable safety rules and emergency procedures |

## Quick start (laptop, simulation) — full runbook in [sim/README.md](sim/README.md)
```bash
make setup                 # venv + editable install
make test                  # unit tests (no SITL) — must be green before any hardware work
make sitl                  # terminal 1: ArduCopter SITL, headless, at Haguenau
make gcs-bridge GCS=<vm>   # terminal 2 (optional): Mission Planner in the Parallels VM spectates (UDP 14550)
make mission-sim           # terminal 3: pymavlink mission + operator dashboard http://localhost:5000
make mission-sim-auto      #   …or fully scripted, no clicking, exits with the results written
```

## Layout
```
config/         base.yaml + sim.yaml / hardware.yaml overlays  ← the ONLY place sim and hardware differ
src/imav_m1/    mission package
  vehicle/      MAVLink abstraction (the only module allowed to import pymavlink) + FakeVehicle for tests
  mission/      state machine, survey pattern generation
  detection/    camera capture, YOLO inference, pixel→GPS georeferencing
  mapping/      pose-tagged image capture, map/orthomosaic output
  config/       YAML profile loader
  cli.py        entry points: run / replay / check-config
sim/            SITL setup, start locations, scripted test scenarios
tests/          unit/ (fast, no SITL) and integration/ (marked `sitl`)
scripts/        start_sitl.sh, run_mission.sh, preflight.sh
hardware/       ArduPilot param dumps (dated), camera calibration
data/           flight logs, datasets, model weights (git-ignored; see data/README.md)
docs/           notes, log, requirements, decisions, hardware, safety, templates
tools/          log analysis / plotting helpers
```

## Workflow (the loop)
1. Write or change code on a branch. Keep diffs small.
2. `make test` green. Add a unit test for any new mission logic (use `FakeVehicle`).
3. Run it in SITL (`make sitl` + `make mission-sim`). Fill a `docs/templates/sim_run_report.md`.
4. Append to `docs/PROGRESS_LOG.md` (commit hash, profile, what, how tested, result, next).
5. Hardware only after **every** box in `docs/SIM_TO_REAL.md` for the current stage is ticked.
6. Every real flight gets a flight test card (`docs/templates/flight_test_card.md`) and a log folder under `data/flights/`.

## Prior work to reuse
The SaR quadrotor project (`~/Desktop/MSc Aerial Robotics/SaR Quadrotor Mission/`) already has a
working pymavlink state machine, survey pattern + waypoint generators, KML parsing, a Pi 5 + IMX296
YOLOv8n detection pipeline with pixel→GPS estimation, and a `--fake` replay mode.
Port, don't rewrite. See `docs/WORKING_NOTES.md` → "Reuse candidates".
