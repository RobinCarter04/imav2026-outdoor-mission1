# CLAUDE.md — context for AI assistants working in this repo

## What this is
Autonomous mapping-and-detection mission (IMAV 2026 **Outdoor Mission 1**) for an ArduPilot quadrotor
with a Raspberry Pi 5 companion computer. Competition: **21–25 Sep 2026, Strasbourg**. Rulebook V4
(1 Sep 2026) lives in `docs/project/rulebook/`. Developed simulation-first (ArduPilot SITL), then moved to
hardware through the gate in `docs/SIM_TO_REAL.md`.

Owner: Robin Carter. Prior working code to port from: `~/Desktop/MSc Aerial Robotics/SaR Quadrotor Mission/`
(see `docs/project/WORKING_NOTES.md` §3 for the file-by-file map).

## Stack
Python ≥ 3.10 · pymavlink · ArduCopter (Cube Orange) · MAVProxy bridge on the Pi · SITL for sim ·
IMX296 global-shutter downward camera · YOLOv8n TFLite detector · YAML config profiles.
No ROS, no PX4, no Gazebo. macOS laptop for dev; Pi 5 (Python 3.13) on the aircraft.

## Commands
```
make setup          venv + editable install
make test           unit tests, no SITL  ← run before saying any task is done
make lint / fmt     ruff
make launch [GCS=<host>]     ONE COMMAND sim session: SITL + mission (+ MP bridge), a Terminal window each (docs/LAUNCH.md)
make stop                    stop SITL + bridge + mission
make sitl / sitl-stop        SITL only, prebuilt binary (never sim_vehicle.py on macOS: it opens a Terminal window)
make gcs-bridge GCS=<vm>     MAVProxy → Mission Planner in the Parallels VM
make mission-sim[-auto]      run mission against SITL (dashboard / scripted)
make plan-sim                offline survey plan preview
make check-config PROFILE=hardware
```

## Architecture (ADR-006..009)
- `mission/framework.py` = the SaR state machine (enter/execute/exit, registry, shared dict, SharedStatus).
  States live in `mission/states/`, one file each, registered in `states/__init__.py`. Operator commands are
  dicts `{"type": ...}` from the dashboard, a trigger file, or the `--auto` script — all equivalent.
- Mission = one AUTO upload: DO_CHANGE_SPEED → survey lines (`mission/survey.py`, no hard-coded coords)
  → transit → NAV_LAND at `landing.point`. TAKEOFF is GUIDED, then AUTO. Never fight the pilot/failsafes.
- Detector is a separate process over `detection/link.py` (docs/DETECTION_INTERFACE.md).
- Whole mission runs in unit tests on `FakeVehicle` (tests/unit/test_state_machine.py) — add a scenario there
  for every new state or transition.

## Layout rules (enforced by tests where possible)
- `config/base.yaml` + `sim.yaml` | `hardware.yaml` are the ONLY place sim and hardware differ.
  Mission code never branches on the profile name.
- `pymavlink` is imported only inside `src/imav_m1/vehicle/`. Everything else uses the `Vehicle`
  protocol (`vehicle/interface.py`) and is unit-tested with `FakeVehicle`.
- `hardware.yaml` safety values may only be more conservative than `base.yaml`.

## Hard rules for AI changes (read `docs/SAFETY.md`)
1. Do NOT modify `config/hardware.yaml`, any `safety:` block, or anything in `hardware/params/` unless
   the human explicitly asks for that specific change in the current conversation.
2. Do NOT write code that bypasses pre-arm checks, disables failsafes/fence, or arms automatically.
3. Do NOT invent rulebook facts. Cite `docs/project/rulebook/<file>` with a section number, or write `TBD`.
4. Every change to `mission/` or `vehicle/` gets a unit test. `make test` must be green.
5. Prefer porting from the SaR project over rewriting. Say which file you ported from.
6. Keep diffs small and single-purpose. Don't refactor unrelated code in passing.
7. Before finishing a session that changed code or ran anything: append an entry to
   `docs/project/PROGRESS_LOG.md` (commit, profile, what, how tested, result, next). Record non-obvious
   choices in `docs/project/DECISIONS.md`.
8. Flag anything that looks unsafe or contradicts the rulebook instead of silently working around it.

## Docs layout
Operational (needed to fly): `docs/HUMAN-REFERENCE.md`, `LAUNCH.md`, `SAFETY.md`, `SIM_TO_REAL.md`,
`HARDWARE.md`, `DETECTION_INTERFACE.md`, `AI-GUIDE.md`, `templates/`.
Background (planning + history, not needed to fly): `docs/project/` — decisions, progress log,
working notes, requirements, rulebook extract.

## Where things are decided
`docs/project/REQUIREMENTS.md` (what "done" means) · `docs/project/DECISIONS.md` (why) · `docs/HARDWARE.md` (what flies)
· `docs/project/WORKING_NOTES.md` (open questions — check before asking the human something already answered)
· `docs/LAUNCH.md` (how a session is started, on the laptop and on the Pi).
