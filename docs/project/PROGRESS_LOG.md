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

## 2026-09-12 (latest) — Geotagging chain ported from SaR; detector boundary moved down to pixels
- Who: Robin (with Claude)
- Commit: this one   Profile: sim   Site: n/a (offline)
- Changed: ADR-013. The detection teammate now supplies bounding boxes in pixels with a frame
  timestamp, and we own everything after that. New `detection/georef.py` (projection + `PoseBuffer`
  interpolated to the frame time), `detection/aggregate.py` (`VehicleAggregator`: world-space
  clustering, one row per vehicle), `detection/geotag.py` (offline runner:
  `python -m imav_m1.detection.geotag --run-dir …`). Ported from SaR
  `robin_package/passive_watch.py` — `DummyEstimator` and `SmartEstimator`. `ATTITUDE` is now read
  into `Telemetry.pitch_deg`/`roll_deg` and written to `telemetry.jsonl`. New config under
  `detection.georef` and `detection.aggregate`.
- Tested: unit — 105 pass (31 new: `test_georef.py` 17, `test_aggregate.py` 14), lint clean. The
  end-to-end test flies a synthetic pass over one truck, projects 5 frames and recovers the position
  to within 1 m. No SITL and no hardware involved; nothing in the flight path changed.
- Result: PASS — the chain runs end to end on files alone.
- Learned / surprises:
  - **The two SaR projection branches disagree by 90°.** Flat-earth treats image-up as forward; the
    ray-trace feeds image-x in as the forward component. Anything geotagged with the ray-trace branch
    is rotated. Only one path is ported.
  - **`telemetry.jsonl` had no pitch or roll**, and nothing subscribed to `ATTITUDE`. At 60 m, 5° of
    cruise pitch is 5.2 m of along-track error — more than the entire 5 m tolerance (§5.4.1). This
    was a silent ceiling on accuracy that no amount of detector work would have lifted.
  - Pose was being taken as "latest value", SaR-style. Fine for a hover, ~1 m per 100 ms at 10 m/s.
  - Clustering in world coordinates removes the need for a frame-to-frame tracker entirely, and keeps
    the class label that Ilias's SORT stage discards.
- Next: (1) `position_error_floor_m` is a guess (3 m) until ground truth is surveyed — it decides what
  passes the 5 m gate; (2) `camera.hfov_deg` is still null, so `Camera.from_config` refuses to run —
  measure it; (3) agree the `raw_detections.jsonl` contract with the detection teammate; (4) decide
  whether the detector writes raw boxes live or we geotag post-flight (both work, same code).

## 2026-09-12 (later) — Slot guard and detection acceptance ported from the team's outdoor FSM
- Who: Robin (with Claude)
- Commit: this one   Profile: sim   Site: imav
- Changed: reviewed Ziyan Lei's `imav2026_vision_fsm` and adopted its two strongest rules (ADR-012).
  **Slot guard**: `mission.slot_duration_s` / `return_margin_s` (1800/300). When the margin is spent,
  SURVEY jumps the autopilot to the first nav item after the survey and hands to RETURN_LAND — a
  normal return, not an abort, so results are still written. **Detection acceptance**:
  `detection/filter.py` requires a label, confidence ≥ 0.5 and any reported position error ≤ 5 m, and
  merges repeats by id then by same class within 10 m. Rejections and reasons go into `summary.json`;
  the map now draws the accepted set so it matches the table. Dashboard shows the slot countdown and
  the accepted/rejected counts.
- Tested: `make test` **74 passed** (12 new filter tests, 3 new mission tests), lint clean.
  **Real SITL, mid-survey cut:** guard fired at 3/14 survey lines, ArduPilot honoured MISSION_SET_CURRENT
  to item 16, flew the return leg, landed, and the table still carried the 2 vehicles found before the
  cut (`data/flights/2026-09-12_sim_02_slotmid`). A second run with a longer slot completed all 14
  lines and reported 3 of 3.
- Result: PASS.
- Learned / surprises: jumping the mission item mid-AUTO is honoured cleanly by ArduPilot, which makes
  the slot guard a route change rather than a second command path — worth remembering for any future
  "cut it short" behaviour. Their FSM has no notion of a safety pilot, flight mode or link loss, which
  is why it is not the thing we fly; noted in the comparison for the team.
- Next: run the teaching session; the four assessment fixes; decide M4 ownership.

## 2026-09-12 (later) — Pushed to GitHub; Pi setup guide; one-command simulator install
- Who: Robin (with Claude)
- Commit: this one   Profile: n/a
- Changed: `docs/PI-SETUP.md` — step-by-step Pi bring-up written for someone new to SSH: connecting
  and every way that fails, getting the code across without GitHub auth on the Pi (rsync) or with a
  token, serial port and dialout setup, a props-off MAVLink check, the bench run, flight-day sequence,
  a tmux cheat sheet and a symptom table. `scripts/setup_sitl.sh` + `make sitl-setup` find or build an
  ArduPilot SITL binary, and `start_sitl.sh` now points at it instead of failing with a bare path.
  Teaching plan gained a day-before message, since the simulator build is 20-40 minutes per laptop.
- Tested: pushed to github.com/RobinCarter04/imav2026-outdoor-mission1 (private); **cold clone
  verified end to end** in a scratch dir — `make setup` installed cleanly, `make test` 59 passed,
  `imav-m1 plan --site fenswood` worked with no simulator present. `setup_sitl.sh --check` finds the
  existing build; the missing-binary path prints the new instructions. Lint clean.
- Result: PASS.
- Learned / surprises: a fresh clone is fully working for tests and planning, but SITL needs a
  separate ~1 GB ArduPilot build per laptop — the old script defaulted to a path only on Robin's Mac,
  so a teammate's first `make launch` would have failed with no explanation. That would have cost the
  teaching session its hands-on block.
- Next: run the session; then the four assessment fixes (results on shutdown, fence read-back,
  home-inside-fence, mission timer).

## 2026-09-12 — Repo reshaped for sharing; teaching, human and AI guides
- Who: Robin (with Claude)
- Commit: this one, on top of `56c7de8`   Profile: n/a (docs + layout)
- Changed: top level now reads as code plus instructions. Operational docs stay in `docs/`
  (HUMAN-REFERENCE, LAUNCH, SAFETY, SIM_TO_REAL, HARDWARE, DETECTION_INTERFACE, AI-GUIDE, templates);
  planning and history moved to `docs/project/` (decisions, progress log, working notes, requirements,
  assessment, rulebook). The 3 MB rulebook PDF is no longer tracked — the text extract and a download
  link remain, since it is the organisers' document to distribute. New `README.md` (five-minute start),
  `docs/HUMAN-REFERENCE.md` (the gotchas that cost an hour each), `docs/AI-GUIDE.md` (using Claude Code
  on this repo safely), `docs/project/TEACHING-PLAN.md` (90-minute session to get the team flying solo).
  Every cross-reference rewritten to the new paths.
- Tested: `make test` 59 passed, lint clean, markdown link check across the repo reports zero broken
  links, `launch_sim.sh --dry-run --site fenswood` unchanged.
- Result: PASS.
- Next: push to GitHub (private), run the teaching session, then the four assessment fixes (results on
  shutdown, fence read-back, home-inside-fence, mission timer).

## 2026-09-10 (later still) — Operator RESUME gate, site switch (Fenswood/IMAV), detector connector
- Who: Robin (with Claude)
- Commit: uncommitted on top of `7d80a68`   Profile: sim   Sites: imav, fenswood
- Changed:
  1. **Manual override tightened.** Inherited behaviour auto-resumed the mission the moment the pilot
     flipped back to GUIDED. Now `MissionState.pilot_override_pause` (shared by SURVEY and RETURN_LAND)
     needs BOTH gates: the pilot returns the aircraft to GUIDED/AUTO, and the operator presses RESUME.
     A RESUME arriving while the pilot still holds it is rejected and not remembered. RTL/LAND/BRAKE
     from pilot or failsafe still aborts without commanding; disarm goes to REPORT. Dashboard gained a
     paused banner and a RESUME button that is disabled until the hand-back. `override_timeout_s` 120 → 300.
  2. **Site layer** (ADR-010): `config/sites/{imav,fenswood}.yaml` selected by `--site`; base → site →
     profile. Fenswood is the SaR flying-day setup ported verbatim from AENGM0074.kml — Flight Area
     fence, SSSI exclusion, Survey Area, Take-Off Location, the SSSI-avoiding corridor, 25 m cruise,
     50 m ceiling, RTL on breach. Exclusion fences and transit corridors are now first-class (ADR-011).
  3. **Detector connector**: `data/flights/latest` pointer, `--detector-cmd` on both launchers (sets
     `IMAV_RUN_DIR` / `IMAV_DASHBOARD`), and `POST /api/detection` as an equal alternative to appending
     to `detections.jsonl`. Documented in `docs/DETECTION_INTERFACE.md`.
  4. **Dashboard API tests** for the operator command route and the detector `POST /api/detection`
     route, including rejection of reports missing lat/lon/cls or with a non-numeric position.
- Tested: `make test` **59 passed**, lint clean. New unit scenarios cover the two-gate resume, refusal
  of an early RESUME, silent timeout-to-abort, and a pilot RTL during override; plus every site planning
  a legal mission, Fenswood's SSSI/corridor, a site being unable to raise the global ceiling, and the
  dashboard HTTP surface.
  **Real SITL, override (re-run after the stick fix below):** all 10 checks passed, driving MAVLink on
  one link and the dashboard over HTTP — pauses on LOITER, refuses the early RESUME, stays paused after
  the hand-back, and commands AUTO only once the operator presses RESUME (`/tmp/override_sitl_test.py`).
  **Real SITL, Fenswood — full mission, DONE:** fence upload 11/11 vertices (4 flight area + 7 SSSI),
  `action=rtl`, `ceiling=50 m` overriding the 75 m cap; corridor out, 20/20 survey waypoints, corridor
  home, NAV_LAND, disarmed at the Take-Off Location, both test vehicles in the submission table.
  Of 267 armed track positions **0 entered the SSSI**; max altitude 25.3 m
  (`data/flights/2026-09-10_sim_15_fenswoodtest`).
- Result: PASS.
- Learned / surprises: raw SITL starts with the simulated throttle stick at MINIMUM, so selecting LOITER
  commands a full descent and the aircraft lands and disarms — it looked like a mission bug until the
  telemetry showed the descent. `scripts/sitl_hold_sticks.sh` holds the sticks centred; GUIDED needs no
  help. Documented in `sim/README.md` §5b.
- Learned / surprises (2): killing a mission process with SIGTERM leaves its placeholder-detector
  subprocess running — Python does not run the `finally` that terminates it. Five had accumulated over
  a session of test runs. `scripts/stop_sim.sh` catches them by name, so the normal path is covered; a
  SIGTERM handler in `cli._run` would close it properly and belongs with the "results on shutdown" fix.
- Note: two Claude sessions worked this task concurrently after an accidental split. Reconciled here —
  duplicated `--site` / `--detector-cmd` options and a duplicated detector-window block in
  `scripts/launch_sim.sh` were removed, and the claims in this entry were re-verified against fresh runs.
- Next: (1) Robin runs `make launch SITE=fenswood` end to end with Mission Planner spectating;
  (2) the four assessment fixes (results on shutdown, fence read-back, home-inside-fence, mission timer);
  (3) drop the teammate's detector in behind `--detector-cmd`.

## 2026-09-10 (later) — One-command launchers for simulation and for the Pi
- Who: Robin (with Claude)
- Commit: uncommitted   Profile: sim
- Changed: `scripts/launch_sim.sh` (opens a Terminal window per stage: SITL → optional MAVProxy bridge
  → mission; waits for SITL's port, settles GPS, opens the dashboard; refuses to start when a stray
  SITL/MAVProxy/mission is running because an idle GCS client freezes SITL; `--dry-run`, `--clean`,
  `--auto`, `--kml`, `--speedup`, `--instance`), `scripts/stop_sim.sh`, and `scripts/launch_hardware.sh`
  for the Pi (preflight gate → MAVProxy bridge → mission → detector, all inside tmux so a dropped SSH
  link cannot kill a flight; `--bench` skips the gate and says the session is not cleared to fly).
  `start_sitl.sh` gained `INSTANCE=N` (ports 5760+10N / 5762+10N, own runtime dir);
  `mavproxy_gcs_bridge.sh` takes the SITL port; `imav-m1 run --connection` overrides the profile.
  New `docs/LAUNCH.md`; `make launch [GCS=…] [KML=…]` and `make stop`.
- Tested: `make test` 33 passed, lint clean. `launch_sim.sh --dry-run` for both the 3-window and the
  headless shapes; stray detection correctly caught two leftover MAVProxy processes. `start_sitl.sh --fg`
  with `INSTANCE=2` opened SERIAL1 on 5782 with its own eeprom, and a mission connected to it and flew
  through setup → preflight → takeoff → survey. `launch_hardware.sh --dry-run --bench` prints the three
  commands and warns that /dev/ttyAMA0 is absent off-Pi.
- Result: PASS, with one caveat: the `open -a Terminal` window-opening step itself has not been run
  (it would put windows on Robin's desktop); everything either side of it is verified.
- Learned / surprises: `open -a Terminal <file>.command` needs no Automation permission, unlike
  osascript, so the launcher generates a small .command per stage under `sim/runtime/launch/`.
- Next: Robin runs `make launch GCS=<vm>` end to end; then the four small fixes from the assessment.

## 2026-09-10 — Competition zones georeferenced from rulebook Fig. 19; survey inset margin; assessment
- Who: Robin (with Claude)
- Commit: `7d80a68` baseline + uncommitted changes below   Profile: sim   SITL: 4.6.0-beta1 hexa, 5×
- Changed: `sim/areas/haguenau_fig19.kml` + `_zones.json` (geofence, flight zone trace, Mapping Areas 1/2,
  fire/drop/dead-man zones, both take-off squares, Tab. 6 sample vehicles) digitised from Fig. 19 after
  fitting the four §5.2 fence corners (1.45 m/px, 1 m residual, ≈ ±10 m overall); check image in
  `docs/rulebook/`. `geo.inset_polygon` + `mission.survey.edge_margin_m` (12 m) so waypoints never touch
  the fence (Area 1 as drawn abuts the flight-zone boundary and overlaps it ~20 m at its SE corner — the
  KML therefore exposes the rulebook geofence as the fence and the traced flight zone as advisory).
  `config/sim.yaml` now flies the drawn Area 1 with landing at the multirotor T/O square; SITL home moved
  there; `imav-m1 run --connection` override; `docs/project/PROGRESS_ASSESSMENT_2026-09-10.md` + status page.
- Tested: `make test` 33 passed, lint clean. `imav-m1 plan --kml sim/areas/haguenau_fig19.kml`: 7 lines,
  3.27 km, ≈5.8 min at 10 m/s. SITL nominal run on the KML area (instance -I1, ports 5770+): 14/14
  waypoints, landed at the T/O square, 3/3 vehicles (`data/flights/2026-09-10_sim_05_fig19area`).
- Result: PASS.
- Learned / surprises: a stopped/idle GCS client on SITL SERIAL0 (a MAVProxy left over from an earlier
  terminal session auto-reconnected to a fresh SITL) stalls the whole simulation — position froze at <1 %
  CPU. Use `-I1` (ports 5770/5772) or kill the stray bridge. `imav-m1 plan --kml` is the fastest sanity
  check of an area file.
- Next: commit this; Robin's runbook run to landing with Mission Planner; team decisions (assessment §5);
  ask organisers which boundary the fence-breach rule applies to (geofence vs black flight-zone line).

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
