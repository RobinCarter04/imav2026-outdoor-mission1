# Progress assessment — 2026-09-10 (11 days to the competition window)

Scope: IMAV 2026 Outdoor Mission 1 (mapping + vehicle identification). Baseline = the first
simulated flight of the ported mission (PROGRESS_LOG 2026-09-08) and Robin's own run on 2026-09-10.

## 1. Where we are

**Working, verified in SITL:** a fully autonomous Mission 1 skeleton on the SaR state-machine
architecture. Operator presses Setup → Preflight → START; the aircraft takes off in GUIDED, flies the
survey in AUTO, transits, lands with NAV_LAND at the configured point, disarms, and the deliverables
(Tab. 6 vehicle table, map, summary, zip) are written automatically with the 5-minute countdown shown.
Pilot override pauses/resumes, failsafes are never fought, operator abort goes RTL, and even an abort
still produces results.

| Evidence | |
|---|---|
| Unit tests | 30 passing, incl. 4 whole-mission scenarios on `FakeVehicle`; lint clean |
| SITL run 01 (08 Sep) | 9/16 waypoints → battery 24 % → ABORT → RTL → results with 1 vehicle (correct behaviour) |
| SITL run 02 (08 Sep) | nominal: 16/16 waypoints, landed at the landing point, 3/3 synthetic vehicles in the table |
| Robin's run (10 Sep) | dashboard-driven, real time: setup, preflight, takeoff, AUTO survey to waypoint 3/16, 1 detection, then stopped at ~5 min while airborne — **no results written** (see §4, gap G-7) |
| Code | ~3.5 k lines in `src/`, 12 states, 3 deliberate stubs (`detection/detector.py`, `detection/georef.py`, `mapping/capture.py`) |
| Docs | rulebook-traced requirements, ADR-001..009, runbook (`sim/README.md`), detector contract, sim-to-real gate, safety rules |
| Repo | **not committed yet** — 15 untracked top-level paths |

Against the 13-day plan in WORKING_NOTES §8, the day 1–3 exit criterion ("flies Area 1 in SITL and
lands") was met on day 1. Days 4–6 (detection + georef + results) are where we are now, with the
detector still in the teammate's hands.

## 2. Requirement status (mirrored into REQUIREMENTS.md)

| Group | Status |
|---|---|
| Autonomous flight (R-01), fence/altitude upload (R-09/10), landing at a point (R-12), results writer (R-06), START as the single manual action (E-09), run reproducibility (E-10) | **verified in SIM** |
| Vehicle table pipeline (R-04) | verified with **synthetic** targets only |
| Map deliverable (R-02) | **placeholder** — track drawing, no imagery |
| Identification (R-05), detector (E-11), image capture (E-03), real georef accuracy (E-04) | **open** — depends on teammate + camera |
| Coverage/timing (R-14, E-01) | estimated only — camera HFOV unknown, fallback 35 m spacing |
| Area 2 (R-03), precision landing (R-12 bonus), self-made doc (R-17) | not attempted (team decision to defer) |
| Weight (R-08), radios (R-13), green card / AlphaTango (R-16) | owned outside this codebase |
| Fault behaviour (E-08), fence params read-back (E-07), KML-on-the-day rehearsal (E-12) | **untested in SITL** |

## 3. What is left (to a competition-ready Mission 1)

1. **Map deliverable** (R-02, autonomy-proof points): pose-tagged image capture on the Pi during the
   survey + a quick georeferenced mosaic that finishes well inside 5 minutes. Format must be confirmed
   with the organisers. This is the largest missing piece and nobody owns it yet.
2. **Detection + identification** (R-04/05): teammate's detector onto `docs/DETECTION_INTERFACE.md`;
   vehicle classes, not persons; decide how brigade letters are obtained (WORKING_NOTES §5, options
   A–D) — this decision drives altitude, GSD and possibly a second pass.
3. **Real survey parameters**: measure the lens HFOV → `camera.hfov_deg`, choose altitude/overlap/speed
   from `tools/coverage_calc.py`, confirm Area 1 fits the slot with battery margin.
4. **SITL fault campaign** (SIM_TO_REAL stage 2): GPS loss, low battery, fence breach → LAND, link loss,
   mission-process kill. Plus the fixes it will surface.
5. **Hardware path**: Pi bring-up (Python 3.13, deps), MAVProxy bridge, bench with props off, param
   dump + hash, camera calibration, first hover, first survey flight, full rehearsal, code freeze.
   The SaR HITL "Sim-on-Hardware" guide is the fastest way to validate the exact Pi ↔ Cube chain.
6. **Competition-day workflow**: draw areas + landing in Mission Planner → KML → `--kml`, rehearsed
   end-to-end in < 5 min; submission drill with a teammate as judge.
7. Optional, points-driven: precision landing (+1 pt/mission), Area 2 (+≈2.7 pts if time allows).

## 4. Corners cut for the first sim fly (honest list)

Deliverables and detection
- **G-1 Map is a placeholder.** `results/mission1_map.svg` draws polygon, fence, track and markers from
  telemetry. No camera frames are captured (`mapping/capture.py` is a stub); the rulebook's "map that
  allows visual identification" is not produced.
- **G-2 Detector is a placeholder process** reporting synthetic targets from the pose stream with
  ±1.5 m noise. No model, no camera, no OCR. `detector.py` / `georef.py` are stubs.
- **G-3 Identification strategy undecided**; the table uses whatever `ident`/`cls` the detector sends.

Planning
- **G-4 Camera FOV unknown**, so line spacing is a fixed 35 m fallback; GSD and coverage time are
  estimates (≈8 sim-minutes for Area 1 at 60 m; est. 6.7). Front overlap / capture interval unused.
- **G-5 Survey planner is minimal**: scanline lawnmower, no lead-in/lead-out, no turn-radius or wind
  model, naive ordering when a scanline crosses a concave polygon more than once, no exclusion zones,
  single polygon only (Area 2 is parsed but never flown).
- **G-6 No mission timer**: nothing enforces the share of the 30-minute slot; a long survey simply runs.

Robustness and safety
- **G-7 No results on an unexpected stop.** Results are written only by REPORT (after landing or
  abort). Ctrl-C / crash mid-flight leaves nothing, and `cv_mode` stays DETECTING (seen in Robin's run).
- **G-8 Fence parameters are fire-and-forget**: `UPLOAD_FENCE` sends FENCE_ENABLE/TYPE/ACTION/ALT_MAX/
  MARGIN without reading them back; preflight verifies the polygon vertex count only. A breach → LAND
  has never been exercised in SITL.
- **G-9 Preflight is thinner than the SaR checklist**: no home-inside-fence check, no RC-failsafe or
  compass/vibration health, no parameter verification, no wind. EKF check uses a fixed flag mask.
- **G-10 No RC consent gate.** TAKEOFF sets GUIDED and arms itself once the operator presses START;
  the SaR "pilot puts the switch in GUIDED first" gate was dropped for full autonomy — team must agree.
- **G-11 Battery abort duplicates the autopilot failsafe** using SYS_STATUS percent; the autopilot's
  own BATT_FS parameters are not set by us, and SITL needed a 30 Ah "pack" (`sim/sitl_params.parm`)
  to finish a survey. On hardware, BATT_CAPACITY must be correct for the percent to mean anything.
- **G-12 Fault scenarios not run** (GPS glitch, link loss, fence breach, process kill); `FakeVehicle`
  has no EKF, no failsafes and instant mode changes, so the unit scenarios are optimistic.

Simulation realism and hardware
- **G-13 SITL only, no wind, default GPS noise, 5× speed-up** for the validation runs; timings are
  sim-time. No dataflash (.BIN) or tlog is collected from SITL runs.
- **G-14 Nothing has touched hardware**: `MavlinkVehicle` has only seen SITL; `hardware.yaml`, the Pi
  MAVProxy bridge and `scripts/run_mission.sh hardware` are untested; no param dump, no calibration.
- **G-15 Fence = rulebook site geofence** when no flight area is given (loud note in the log). The real
  flight area on the day will be smaller.

Code and process
- **G-16 Uncommitted**; `imav-m1 replay` unimplemented; a few `noqa: E501` on SVG/HTML template lines;
  the dashboard is a single inline page polled at 2 Hz with no map tiles.
- **G-17 SITL integration test** only checks a heartbeat; the end-to-end SITL runs were manual.

## 5. Immediate next steps (next 48 h)

1. **Commit the baseline** (`git add -A && git commit`), tag `sim-first-flight`.
2. **Robin:** finish one full dashboard run to landing with Mission Planner spectating; try LOITER →
   GUIDED from Mission Planner mid-survey, and RTL; confirm results.zip appears. Note whether the 10 Sep
   run was a Ctrl-C.
3. **Team meeting decisions (tomorrow):** airframe + all-up mass; lens → HFOV; radios owner; map
   deliverable owner; identification strategy (A–D); accept G-10 (no RC gate)?; who emails the
   organisers about map format, partial-credit for type-only identification, and whether a GCS START
   counts as an in-mission action.
4. **Code, small and test-backed:** (a) REPORT on shutdown — Ctrl-C/stop writes partial results and
   resets `cv_mode` (G-7); (b) read back fence params in preflight (G-8); (c) home-inside-fence check
   (G-9); (d) mission timer with a configurable abort-to-RTL (G-6).
5. **SITL fault campaign** from a MAVProxy console (`sim/README.md` §6), one afternoon, log each in
   PROGRESS_LOG (G-12).
6. **Enter the real HFOV** as soon as it is measured, re-run `imav-m1 plan --profile sim`, fix altitude
   and speed, update `config/base.yaml` and the time budget (G-4).
7. **Start the map prototype** in parallel: capture pose-tagged frames from the Pi camera (or replayed
   video) into `images/` + `images.csv`, then a GSD-placed quick mosaic in `tools/build_map.py` (G-1).
8. **Pi bring-up** this week: clone, install, run the hardware profile against Sim-on-Hardware on the
   bench (SaR HITL guide) before any real flight (G-14).

## 6. Top risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | Brigade letters unreadable at survey altitude → vehicle points lost | decide strategy tomorrow; ask organisers about type-only credit; consider a low second pass |
| 2 | Map format / submission method unknown → deliverable rejected | email organisers now; build the simplest georeferenced mosaic + KML overlay |
| 3 | Hardware time: ~5 days for bench + flights, weather, site access | Sim-on-Hardware bench first; freeze code by day 12 |
| 4 | Radio power limits (2.4/5.8 GHz ≤ 25 mW) could ground us | RF owner confirms every link this week |
| 5 | Fence breach → LAND ends the run in the field | generous flight area, FENCE_MARGIN, breach test in SITL, conservative line spacing at edges |
