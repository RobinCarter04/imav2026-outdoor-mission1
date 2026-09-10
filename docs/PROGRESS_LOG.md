# Progress log — IMAV 2026 Outdoor Mission 1

Newest entry at the top. One entry per work session or per test run.
Every entry that involved running code records the **commit hash** and **config profile** so any
result can be reproduced. Hardware flights additionally get a flight test card in `data/flights/`.

Entry template:
```
## YYYY-MM-DD — <short title>
- Who:
- Commit: `abc1234`   Profile: sim | hardware   Firmware: ArduCopter x.y.z (hw only)
- Changed:
- Tested: (unit / SITL scenario / bench / flight) — how, what scenario, log folder
- Result: PASS / FAIL / PARTIAL — one line of evidence
- Learned / surprises:
- Next:
```

---

## 2026-09-08 — Mission 1 state machine ported from SaR and flown end-to-end in SITL
- Who: Robin (with Claude)
- Commit: — (uncommitted working tree)   Profile: sim   SITL: ArduCopter 4.6.0-beta1 (Group Project checkout), hexa
- Changed: Ported the SaR flying-day architecture into `src/imav_m1/` (ADR-006..009): `mission/framework.py`
  (state machine, SharedStatus), `vehicle/mavlink_vehicle.py` (DroneConnection port), `mission/survey.py`
  (generalised scanline lawnmower, spacing from camera FOV/overlap or `spacing_m`), `mission/area.py`
  (config or KML areas, fence fallback to the §5.2 site geofence), states IDLE → GENERATE_PATTERN →
  UPLOAD_FENCE → UPLOAD_MISSION → PREFLIGHT_CHECK → TAKEOFF → SURVEY → RETURN_LAND → REPORT → DONE (+ ABORT,
  CHANGE_MODE), detector file contract + placeholder detector process, telemetry log, results writer
  (Tab. 6 CSV, map SVG, summary, zip), operator dashboard, `imav-m1 run/plan`, SITL scripts, runbook.
- Tested: `make test` 30 passed (incl. 4 end-to-end scenarios on FakeVehicle: nominal, pilot override
  pause/resume, operator abort → RTL, failsafe not fought); `make lint` clean.
  SITL (5× speed, headless `--auto --no-gui`):
  - run 01: full chain, took off, flew 9/16 survey waypoints, **battery 24 % → ABORT → RTL → disarm → results
    with 1 vehicle** (`data/flights/2026-09-08_sim_01_validate`). Correct behaviour; the stock SITL pack is tiny.
  - run 02 (with `sim/sitl_params.parm` 30 Ah pack): **nominal** — 16/16 waypoints, transit, NAV_LAND at the
    landing point, disarmed, 3/3 synthetic vehicles in `results/mission1_vehicles.csv`, map + zip written,
    114 s sim-wall takeoff→landed (`data/flights/2026-09-08_sim_02_validate2`).
- Result: PASS — Mission 1 skeleton flies in SITL; only the operator's START is manual.
- Learned / surprises:
  - `sim_vehicle.py` on macOS spawns the vehicle in a new Terminal window; run the binary directly.
  - SITL blocks at boot until something connects to SERIAL0 (5760) unless `--serial0 tcp:0:nowait`.
  - Survey of a 440 × 280 m area at 60 m / 35 m spacing / 10 m/s took ≈ 8 sim-minutes (est. 6.7).
  - Placeholder detections land within ~1.5 m of the synthetic targets (noise model) — the georef
    accuracy test (E-04) is ready to be run for real once the teammate's detector arrives.
- Next: (1) Robin: run the three-terminal runbook (`sim/README.md`) with Mission Planner spectating;
  (2) team: confirm airframe/HFOV/radios, decide identification strategy (WORKING_NOTES §5, ADR-006 note);
  (3) drop the teammate's detector onto `docs/DETECTION_INTERFACE.md`; (4) stage-2 fault scenarios in SITL
  (`sim/README.md` §6); (5) first commit.

## 2026-09-08 — Repository scaffold + rulebook V4 digested
- Who: Robin (with Claude)
- Commit: — (scaffold not yet committed)   Profile: sim (config loader only)
- Changed: Project structure; docs (working notes, this log, decisions ADR-001..005, requirements R-01..17 /
  E-01..12, hardware, sim-to-real gate, safety, templates); config profiles base/sim/hardware with the
  §5.2 site geofence and 80 m rule; Python package skeleton (`Vehicle` protocol, `FakeVehicle`, stubs
  marked PORT FROM the SaR project); YAML loader; tests; SITL/preflight scripts; `tools/coverage_calc.py`;
  rulebook V4 PDF + text extract in `docs/rulebook/`.
- Tested: `pytest` → 8 passed, 1 deselected (SITL marker); `ruff check` + `ruff format --check` clean;
  `imav-m1 check-config --profile hardware` prints the merged config; `imav-m1 run --profile sim` exits 2
  "not implemented" as intended.
- Result: PASS — green baseline before any mission code exists.
- Learned / surprises:
  - Competition is 21–25 Sep (13 days). Outdoor field is the Haguenau military ground, not Strasbourg.
  - Mission 1 is *vehicle* identification (CCF/VLTT/VT4/GBC 180/VBL + roof registration letters), not
    people — the SaR person detector does not carry over, the camera/Pi/georef do.
  - Scoring: map points are independent of the autonomy factor; vehicles + 5-min submission are the bulk;
    mass factor is large (2 kg → ×1.66). Area 1+2 probably does not fit the 30-min slot (see notes §3).
  - Radio power limit at 2.4/5.8 GHz is 25 mW — check every link.
- Next: (1) confirm airframe, weight, lens HFOV, radios → `HARDWARE.md`; (2) decide identification
  strategy (notes §5) → ADR-006; (3) port `connection.py` → `vehicle/mavlink_vehicle.py`, get a SITL
  heartbeat via `make mission-sim`; (4) first commit + branch.
