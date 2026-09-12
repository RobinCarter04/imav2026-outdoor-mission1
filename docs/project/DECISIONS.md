# Decision records

Short ADR-style entries. One per non-obvious choice. Status: proposed | accepted | superseded.
New record → copy `templates/decision_record.md`. Never delete a record; supersede it.

---

## ADR-001 — Autopilot & simulation stack: ArduPilot + pymavlink + SITL
- Status: accepted (2026-09-08)
- Context: 13 days to competition. The SaR project has working pymavlink code against ArduCopter on a
  Cube autopilot, and an ArduPilot SITL checkout already exists on this machine.
- Decision: ArduCopter firmware, pymavlink from a Raspberry Pi companion (via MAVProxy UDP bridge on
  hardware, direct TCP to SITL in sim). No ROS, no PX4, no MAVSDK.
- Consequences: fastest path to a flying mission; we inherit the SaR quirks (MAVProxy bridge,
  heartbeat filtering). Gazebo/visual sim is out of scope — camera testing is done by replay.

## ADR-002 — Sim and hardware differ only by config profile
- Status: accepted (2026-09-08)
- Context: the SaR code switched sim/real by commenting lines in `config.py`. Easy to fly the wrong one.
- Decision: `config/base.yaml` + `config/sim.yaml` | `config/hardware.yaml` overlays, selected by
  `--profile`. Mission logic never branches on the profile. `hardware.yaml` may only make safety values
  more conservative than `base.yaml` (enforced by a unit test).
- Consequences: one code path is tested in SITL and flown on hardware. Profile is recorded in every
  log entry and `run.yaml`.

## ADR-003 — Vehicle abstraction: pymavlink lives only in `vehicle/`
- Status: accepted (2026-09-08)
- Context: mission logic tangled with MAVLink calls cannot be unit-tested without a vehicle.
- Decision: `vehicle/interface.py` defines the `Vehicle` protocol; `MavlinkVehicle` implements it;
  `FakeVehicle` is an in-memory implementation for unit tests. Mission/detection code imports only the
  interface.
- Consequences: state machine and survey logic get fast unit tests; MAVLink bugs are isolated to one
  module.

## ADR-004 — Companion computer + camera carried over from SaR project
- Status: proposed — confirm airframe and camera mount before accepting
- Context: Pi 5 + IMX296 global-shutter (1456×1088) downward camera + YOLOv8n TFLite proven at 20–40 m.
- Decision (proposed): reuse as-is. Re-run camera intrinsics calibration; verify frame rate with
  full-resolution mapping capture running alongside detection.
- Consequences: no new hardware integration risk; GSD at mission altitude must be checked against target
  size in the rulebook.
- **Update 2026-09-08:** Mission 1 targets are vehicles (CCF / VLTT / VT4 / GBC 180 / VBL + roof registration
  letters, §5.4.1), not people. Camera, Pi and georef carry over; the person model does not. The
  identification strategy (WORKING_NOTES §5) needs its own ADR-006 by day 3.

## ADR-005 — Camera-in-the-loop by replay + synthetic targets, not Gazebo
- Status: accepted (2026-09-08)
- Context: no time to set up Gazebo camera plugins on macOS; detector behaviour is what matters.
- Decision: `imav-m1 replay` feeds recorded/synthetic frames with a scripted pose track through the
  real detector + georef code. Synthetic targets at known coordinates give a georef accuracy metric.
- Consequences: no closed-loop "see target → change flight path" testing in sim. Acceptable for a
  fixed survey pattern; revisit if the mission rewards reactive behaviour.

## ADR-006 — Keep the SaR state-machine architecture (ported, not redesigned)
- Status: accepted (2026-09-08)
- Context: the SaR flying-day state machine (string-named states with enter/execute/exit, a registry
  dict, a `shared` data bag, subroutine states with `return_to`, `SharedStatus` bridging to a Flask
  dashboard) proved flexible and robust against added capabilities. Robin wants that intact.
- Decision: port `machine.py` / `states/base.py` / `shared.py` into `mission/framework.py` unchanged in
  spirit; states get a `MissionContext` (vehicle, cfg, shared, status, sleep, run_dir, detector,
  telemetry log) and pass time through `ctx.sleep()` so the whole mission runs in unit tests on
  `FakeVehicle` without wall time. Added a return *stack* for chained subroutines and a clean `_stop`.
- Consequences: new capabilities are new state files + a registry entry; operator commands are plain
  dicts so the dashboard, a trigger file and the `--auto` script are interchangeable.

## ADR-007 — Detector runs as a separate process over a file contract
- Status: accepted (2026-09-08)
- Context: a teammate owns detection + geotagging; it must slot in later with zero shared code. The
  SaR `cv_comm.py` mode-file idea worked in the field.
- Decision: `detection/link.py` — mission writes `detections/cv_mode` (PASSIVE|DETECTING) and a
  `telemetry.jsonl` pose stream; the detector appends `detections/detections.jsonl`. A placeholder
  detector (`detection/placeholder.py`) reports synthetic targets so the whole pipeline (survey →
  detections → Tab. 6 table + map) is exercised in SITL today. Contract in `docs/DETECTION_INTERFACE.md`.
- Consequences: the detector never commands the aircraft; the mission never blocks on it. Onboard
  processing (A1 = 1) stays possible because both run on the Pi.

## ADR-008 — Landing = NAV_LAND at a landing point inside the AUTO mission (precision landing deferred)
- Status: proposed (2026-09-08) — revisit once the core flies on hardware
- Context: rulebook §5.2.1 / §5.3.3 gives +1 pt for a 1 × 1 m ArUco landing vs the 3 × 3 m zone; the
  team decided to ignore precision landing for now.
- Decision: the uploaded mission ends with a transit waypoint + NAV_LAND at `landing.point` (given
  on the day) so ArduPilot owns the whole sequence; `RETURN_LAND` monitors and falls back to LAND mode.
  `landing.precision` (NAV_LAND p2) is the hook for ArduPilot precision landing later.
- Consequences: one robust code path now; precision landing is an additive change (PLND params +
  LANDING_TARGET from the Pi), not a rewrite.

## ADR-009 — SITL by running the arducopter binary directly; MAVProxy only as a GCS bridge
- Status: accepted (2026-09-08)
- Context: `sim_vehicle.py` on macOS launches the vehicle in a new Terminal window, so headless runs
  and scripts never see it. A prebuilt 4.6.0-beta1 SITL binary exists in the Group Project checkout.
- Decision: `scripts/start_sitl.sh` runs `build/sitl/bin/arducopter` headless (hexa frame, Haguenau
  home from `sim/locations.txt`); the mission code connects to SERIAL1 (tcp 5762); Mission Planner in
  the Parallels VM spectates via `scripts/mavproxy_gcs_bridge.sh` (UDP 14550, as on the SaR flying
  days) or straight TCP to SERIAL2 (5763).
- Consequences: three terminals, no GUI dependencies on the Mac, same port layout as the aircraft
  (mission code on its own link, GCS on another).

## ADR-010 — Site is a third config layer, orthogonal to the sim/hardware profile
- Status: accepted (2026-09-10)
- Context: we need to fly the same code at Fenswood (test flights, SaR areas, an SSSI no-fly zone)
  and at Haguenau (IMAV Mission 1). Site geography is independent of whether the code runs in SITL
  or on the Pi, so folding it into `sim.yaml` would have forced four files and duplicated geometry.
- Decision: `config/base.yaml` (defaults + safety caps) → `config/sites/<site>.yaml` (WHERE: flight
  area, exclusions, transit corridor, survey polygon, landing point, ceiling, breach action, SITL
  home) → `config/<profile>.yaml` (HOW the code runs: link and camera source only). Selected with
  `--site imav|fenswood` on every command and `--site`/`SITE=` on the launcher; the default comes
  from `base.yaml site.name`. A site file never edits the `safety:` block itself: `effective_max_alt_m`
  and `effective_fence_action` are the single places that combine site and global limits, and a site
  can only ever tighten the ceiling.
- Consequences: adding a test field is one YAML file. Sites are covered by tests that assert every
  configured site plans a legal mission (inside its fence, clear of its exclusions, below its ceiling).

## ADR-011 — Exclusion zones and transit corridors are first-class
- Status: accepted (2026-09-10)
- Context: Fenswood's SSSI is a protected no-fly area sitting between the take-off point and the
  survey area, so a straight run in would cross it. SaR solved this with hand-listed corridor
  waypoints (SSSI_NAV_TO_SEARCH / _TO_HOME).
- Decision: sites declare `exclusions` and `transit_to_survey` / `transit_to_home`. Exclusions are
  uploaded as MAVLink exclusion fences in the same transaction as the inclusion fence (an upload
  replaces the autopilot's whole list). The corridors become mission waypoints before and after the
  survey, flown at `transit_speed_mps`. Loading refuses any survey waypoint, landing point or
  corridor waypoint that falls inside an exclusion.
- Consequences: Fenswood flies the same route SaR flew. IMAV declares no exclusions, so nothing changes there.
