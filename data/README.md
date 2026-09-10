# data/ — flight logs, datasets, model weights (git-ignored)

Everything here is git-ignored except this file, `models/MANIFEST.md`, and `.gitkeep`s.
Back it up separately (external drive / cloud) — it is NOT in version control.

## flights/  — one folder per run, sim or hardware
Name: `YYYY-MM-DD_<sim|hw>_<NN>_<short-desc>/`   e.g. `2026-09-10_sim_03_lawnmower-30m/`

Each folder should contain:
| File | Purpose |
|---|---|
| `run.yaml` | git commit, config profile, full merged config snapshot, firmware version, param file hash, operator |
| `mission.log` | human-readable log written by the mission code |
| `*.tlog` / `*.BIN` | MAVLink telemetry log / ArduPilot dataflash log |
| `images/` | pose-tagged captures for mapping |
| `detections/` | detection images with GPS in filename (as in the SaR pipeline) |
| `report.md` | filled-in `docs/templates/sim_run_report.md` or `flight_test_card.md` |

The mission code should create `run.yaml` automatically at startup (TODO — see `docs/WORKING_NOTES.md`).

## datasets/
Recorded videos / image sets for `--replay` testing and detector evaluation. Note source, date, altitude, camera.

## models/
Detector weights. Every file listed in `MANIFEST.md` with sha256, source, input size, classes.
