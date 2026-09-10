# Sim-to-real gate

Code reaches the aircraft only by passing each stage in order. Tick boxes in a copy attached to the
relevant PROGRESS_LOG entry. If a stage fails, go back one stage — do not "just try it on the drone".

## Stage 0 — Unit tests (every change)
- [ ] `make test` green and `make lint` clean
- [ ] New mission logic has a test against `FakeVehicle`
- [ ] No pymavlink import outside `src/imav_m1/vehicle/`
- [ ] `config/hardware.yaml` safety values ≥ as conservative as `base.yaml` (test enforces)

## Stage 1 — SITL nominal
- [ ] Full mission in SITL from the competition location: takeoff → survey → RTL → land
- [ ] Deliverables produced (map images + results file) and validated by hand
- [ ] Mission time and estimated battery use within limits
- [ ] Sim run report filed in `data/flights/`

## Stage 2 — SITL faults
- [ ] Link loss mid-survey → autopilot failsafe RTL, mission code does not fight it
- [ ] Fence breach injected → fence action, mission code exits cleanly
- [ ] Battery failsafe injected → RTL/land
- [ ] GPS glitch injected (`SIM_GPS_DISABLE`) → EKF failsafe behaves, code recovers or aborts
- [ ] Mission code crash (kill -9) mid-flight → aircraft continues/RTLs safely on its own

## Stage 3 — Bench, props OFF
- [ ] Pi ↔ Cube link: heartbeat from component 1, mode changes round-trip
- [ ] Real camera + detector running at target frame rate; Pi temperature stable after 10 min
- [ ] Param file dumped to `hardware/params/` and hash recorded in `HARDWARE.md`
- [ ] RC failsafe, fence, battery failsafe parameters verified in GCS
- [ ] Aircraft weighed; below MTOW

## Stage 4 — First flights (safety pilot on sticks, small area)
- [ ] Manual hover — vibration, compass, EKF healthy in logs
- [ ] Autonomous takeoff + 2-line survey + RTL, safety pilot ready to take over
- [ ] Georef check: known ground marker vs reported coordinates, error recorded
- [ ] Flight test card filed

## Stage 5 — Full rehearsal
- [ ] Complete mission on a competition-sized area, timed, deliverables submitted to a teammate as judge
- [ ] Repeat once from a cold boot with no code changes
- [ ] Tag the commit `comp-freeze`; only config/param changes after this, each logged

## Known sim ≠ real differences (check each against the mission)
| Difference | Risk | Mitigation |
|---|---|---|
| GPS/EKF noise, compass interference | georef error, EKF failsafes | Stage 4 marker test; compass cal away from metal |
| Wind | drift between survey lines, battery use | overlap margin; endurance × 1.3 |
| Camera exposure / motion blur at real light levels | detector misses | global shutter helps; test at similar time of day |
| Pi thermal throttling | frame drops | active cooling; Stage 3 soak test |
| MAVProxy bridge latency | slow mode changes | timeouts from SaR (`MODE_CHANGE_TIMEOUT` 10 s) |
| SITL "perfect" takeoff | real takeoff needs pre-arm checks passing | never bypass pre-arm |
