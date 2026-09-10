# Requirements — traced to rulebook V4 (1 Sep 2026)

Status column last updated 2026-09-10 (see PROGRESS_ASSESSMENT_2026-09-10.md).

Every requirement has an ID, a rulebook reference, and a verification method. "Done" means every **M**
row is verified. Citations are to `rulebook/Rulebook_IMAV2026_V4-1.pdf` (text: `.txt` alongside).
Update the ref column if a V5 appears.

Priority: M = must (a rule, or scores directly) · S = should · C = could.
Verify: UT = unit test · SIM = SITL scenario · REPLAY = detector on recorded/synthetic frames · BENCH = props-off ·
FLT = flight test · DOC = document / checklist.

## Mission requirements
| ID | Requirement | Pri | Rulebook ref | Verify | Status |
|---|---|---|---|---|---|
| R-01 | Flight fully autonomous with a safety pilot present; manual flight control prohibited; any manual action during the mission (mode change, switch, GCS action) drops the autonomy factor to 0.4 | M | §2, §2.2, §5.3.1 | SIM, FLT | SIM ✔ nominal + abort (08 Sep); FLT open |
| R-02 | Produce a map of Mapping Area 1 (440 × 280 m) on which vehicles are visually identifiable (Z = 2 pts) | M | §5.4.1, Tab. 7 | SIM, DOC | placeholder map (track SVG, no imagery) |
| R-03 | Extend the map to Mapping Area 2 (+440 × 320 m) (Z = 4 pts) — only if the time budget allows | S | §5.4.1, Tab. 7 | SIM (timed) | not attempted |
| R-04 | Submit a table `Vehicle \| Identification \| GPS` in decimal degrees for each vehicle, positions within 5 m (0.375 pts per vehicle, 8 vehicles) | M | §5.4.1, Tab. 6, Tab. 7 | UT (writer), REPLAY (accuracy), FLT | pipeline SIM ✔ (synthetic targets); real detector open |
| R-05 | Identify fire vehicles as CCF (truck) or VLTT (light 4×4) plus brigade (last 3 letters of the roof registration); military as VT4, GBC 180 or VBL | M | §5.4.1 | REPLAY, FLT | open — strategy undecided (notes §5) |
| R-06 | Submit map + table ≤ 5 min after landing (R = 2); ≤ 30 min gives R = 1 | M | §5.4.1, Tab. 7 | DOC (timed drill) | writer ✔ on landing; timed drill + format TBC |
| R-07 | All computation onboard (A1 = 1); off-board processing is the A1 = 0.7 fallback | S | §2, §5.3.1 | DOC | by design (all onboard); detector TBD |
| R-08 | Takeoff weight ≤ 5 kg incl. battery and payload; wingspan ≤ 3 m; lighter is rewarded by W1 = 2·(1 − e^(−5/(1.4·W))) | M | §2, §5.3.2, Tab. 7 | DOC (weigh) | open (weigh) |
| R-09 | Never above 80 m AGL | M | §2 | SIM (fence), FLT | FENCE_ALT_MAX 75 set in SIM; breach untested |
| R-10 | Stay inside the site geofence (four corners in §5.2) and the flight area marked on the day; leaving the zone → land; further → motor cut | M | §2, §5.2 | SIM (breach → land), BENCH (params) | polygon uploaded in SIM ✔; breach → land untested |
| R-11 | Kill switch on the RC transmitter | M | §2 | BENCH | open (hardware) |
| R-12 | Return to the designated landing area (mission validated only then); land inside the 3 × 3 m zone (1 pt) or within 1 × 1 m on the 80 cm ArUco 5x5 marker (2 pts) | S | §2.2, §5.2.1, §5.3.3 | SIM, FLT | NAV_LAND at point ✔ SIM; zone/ArUco open |
| R-13 | Radio links within French limits: 2.4 GHz ≤ 25 mW, 5.8 GHz ≤ 25 mW, 863–868 MHz ≤ 25 mW, 433 MHz ≤ 10 mW | M | §2.1, Tab. 1 | DOC (check every link) | open (RF owner) |
| R-14 | Whole mission (setup, flight, deliverables) fits its share of the 30-min team slot; 10 min prep beforehand | M | §2.2, §5.4 | SIM (timed), DOC | ≈8 sim-min Area 1 @ 60 m / 35 m; HFOV unknown |
| R-15 | Accept the area polygon, landing zone and ArUco ID as inputs on competition day, quickly and verifiably | M | §5.2 | UT, DOC (rehearsed) | KML path implemented; unit-tested only |
| R-16 | Green card obtained on the training day; pilots hold the AlphaTango qualification; ID/passport on site | M | §2, §2.2, §5.1, §5.2 | DOC | open (admin) |
| R-17 | Technical document for self-made design points (SF1 ≤ 2 pts) | C | §5.3.4 | DOC | open |

## Derived engineering requirements
| ID | Requirement | From | Verify | Status |
|---|---|---|---|---|
| E-01 | Survey plan (altitude, side overlap, speed) covers Area 1 within the time budget with ≥ 1.3× battery margin — `tools/coverage_calc.py` with the calibrated HFOV | R-02, R-14 | DOC (calc), SIM (timed), FLT | fallback spacing only — needs HFOV |
| E-02 | Ground sample distance sufficient to classify vehicle type; strategy for brigade letters decided (ADR) | R-05 | REPLAY | open |
| E-03 | Every mapping image tagged with pose (lat, lon, alt, yaw, roll, pitch, t) | R-02 | UT, SIM | telemetry only; no images |
| E-04 | Vehicle georeferencing error ≤ 3 m on synthetic targets (margin against the 5 m rule); ground-marker check in flight | R-04 | UT, FLT | placeholder ±1.5 m; real georef open |
| E-05 | Map and Tab. 6 table written automatically on landing, in < 2 min on the laptop or Pi | R-06 | DOC (timed drill) | ✔ SIM (< 1 s) |
| E-06 | Line spacing derived from camera footprint and overlap; capture interval from front overlap and speed | R-02 | UT | code ✔; FOV path untested for real |
| E-07 | ArduPilot fence: polygon inclusion + `FENCE_ALT_MAX` ≤ 75 m, breach action LAND, verified in params dump | R-09, R-10 | SIM, BENCH | params sent fire-and-forget — not read back |
| E-08 | Mission aborts to the autopilot's failsafe on link loss / battery / fence breach without fighting it | R-10, SAFETY | SIM | UT ✔; SIM faults not injected |
| E-09 | Arming needs an explicit operator trigger before the mission starts; nothing manual afterwards | R-01, SAFETY | UT, BENCH | ✔ (dashboard START) |
| E-10 | `run.yaml` written at startup: commit, profile, merged config, firmware, param hash | reproducibility | UT | ✔ run.yaml |
| E-11 | Detector covers vehicle classes (CCF, VLTT, VT4, GBC 180, VBL), not persons; evaluation set from rulebook figures + own imagery | R-05 | REPLAY | open (teammate) |
| E-12 | Polygon input path (KML from Mission Planner → config) rehearsed end-to-end in < 5 min | R-15 | DOC | open — rehearse with MP KML |
