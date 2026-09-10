# Working notes — IMAV 2026 Outdoor Mission 1

Scratchpad. Messy is fine. When something here becomes a *fact* or a *decision*, promote it:
requirements → `REQUIREMENTS.md`, choices → `DECISIONS.md`, hardware facts → `HARDWARE.md`,
dated outcomes → `PROGRESS_LOG.md`. Then delete or shorten it here.
Rulebook citations (§x.y) refer to V4 — grep `rulebook/Rulebook_IMAV2026_V4-1.txt`.

---

## 0. Reality check (2026-09-08)
- Competition **21–25 Sep 2026**. Outdoor flying at the **Haguenau military training ground** (§3.2, §5.2),
  ~45 min from Strasbourg; a bus runs from INSA on the test and competition days. Bring ID/passport (§5.2).
- **13 days** from today, including travel. Rulebook at **V4 (1 Sep)** — rules moved a week ago; check
  https://2026.imavs.org/competitions-rulebook-imav-2026/ for a V5 before every planning session.
- This is a *port-and-harden* project. Reuse the SaR pipeline, change only what Mission 1 needs, spend
  the saved time on SITL rehearsals and one or two real flights.

## 1. Mission 1 on one page (§5.4.1–5.4.2, Tab. 6–7; general rules §2, §2.2, §5.2, §5.3)
- Name: "Mapping and vehicule identification". Two deliverables:
  1. **A map** of the area on which the vehicles are visually identifiable.
  2. **A table**: `Vehicle | Identification | GPS` in decimal degrees, e.g. `67-CCF-M-ING | 48.8095202 ; 7.8520274` (Tab. 6).
- Areas: **Mapping Area 1 = 440 × 280 m**; **Mapping Area 2 = +440 × 320 m**. Corner coordinates and
  landing zones are **given on the day** (§5.2) → the mission must accept a polygon as input quickly.
- Vehicles: **8** in total (Tab. 7). Fire brigade: **CCF** (truck) or **VLTT** (light 4×4), and the brigade =
  last 3 letters of the roof registration (`67-CCF-M-ING` → INGwiller); roofs white or yellow. Military:
  **VT4** (4×4), **GBC 180** (truck), **VBL** (light armoured). Fire/military split told on the day.
- Accuracy: GPS within **5 m**. Submission **≤ 5 min after landing** for full time points (≤ 30 min for half).
- Scoring (Tab. 7): **S1 = 0.8 · (Z + nV · R · A1) · W1 + La1 + SF1**
  - Z: 2 pts for the Area 1 map, 4 pts for Area 1 + 2. **Not multiplied by the autonomy factor.**
  - nV: 0.375 pts per vehicle (identified + positioned), max 3 pts for 8 vehicles.
  - R: 2 if submitted ≤ 5 min after the flight, 1 if ≤ 30 min.
  - A1: 1 all computation onboard · 0.7 off-board computation · 0.4 any manual action during the mission
    (mode change, switch, action on the GCS). Manual *flight* control is prohibited outright (§2, §5.3.1).
  - W1 = 2·(1 − e^(−5 / (1.4·W_uav))), W in kg → 1 kg: 1.94 · 1.5 kg: 1.81 · 2 kg: 1.66 · 3 kg: 1.39 · 5 kg: 1.02
  - La1: 2 pts precision landing (1 × 1 m on an 80 cm ArUco 5x5), 1 pt inside the 3 × 3 m zone (§5.2.1, §5.3.3).
  - SF1: up to 2 pts for >50 % self-made design, from the technical document (§5.3.4).
- General rules that bite (§2, §2.1, §2.2): MTOW **5 kg** incl. battery + payload · **kill switch on the RC
  mandatory** · max **80 m AGL** · flights fully autonomous with a safety pilot · leave the flight zone → land,
  further → motor cut · radio power limits **2.4 GHz 25 mW, 5.8 GHz 25 mW, 868 MHz 25 mW, 433 MHz 10 mW** ·
  green card on the training day · pilots need the AlphaTango qualification · **30-min slot for all four
  missions**, 10 min prep · a mission counts only once the drone is back in its landing area.

## 2. Points economics → priorities
Worked example at W = 2 kg (W1 = 1.66), 8 vehicles found, table submitted within 5 min:
| Scenario | Z | nV·R·A1 | 0.8·(…)·W1 |
|---|---|---|---|
| Area 1, all onboard | 2 | 6 | **10.6** |
| Area 1, off-board processing (A = 0.7) | 2 | 4.2 | 8.2 |
| Area 1 + 2, all onboard | 4 | 6 | 13.3 |
| Area 1, onboard, no vehicle found | 2 | 0 | 2.7 |
Takeaways:
1. **The map alone is cheap and autonomy-proof** (Z is outside the A1 bracket): fly the survey, stitch, submit.
   Secure this first — it is also the prerequisite for everything else.
2. **Vehicles are the bulk**: ≈ 8 pts at A = 1. Off-board processing costs ≈ 2.4 pts; one manual action ≈ 4.8.
3. **Area 2 ≈ +2.7 pts for roughly double the flight time** — only if the time budget in §3 allows.
4. **Precision landing** is +1 pt over a zone landing and applies to every mission flown in that flight.
   ArduPilot precision landing + ArUco detection on the Pi is a known recipe. After the core works.
5. **Mass**: every 500 g is worth ~5–8 % of the mission score. Weigh the aircraft this week.
6. **Submission within 5 min doubles R** → the results table + map must be written automatically on landing.

## 3. Coverage / time budget (`tools/coverage_calc.py`)
Assumptions: nadir IMX296 (1456 px wide), lines along the 440 m axis, 10 m/s, 4 s per turn,
**HFOV 45° (assumed 6 mm lens — replace with the calibrated value)**, Area 1 + 2 assumed adjacent (440 × 600 m).

| HFOV° | alt m | side ov | area | footprint m | GSD cm/px | spacing m | lines | path km | min @10 m/s |
|---|---|---|---|---|---|---|---|---|---|
| 45 | 40 | 0.30 | Area 1 | 33 | 2.3 | 23 | 14 | 6.5 | 11.6 |
| 45 | 40 | 0.30 | Area 1+2 | 33 | 2.3 | 23 | 27 | 12.5 | 22.5 |
| 45 | 40 | 0.50 | Area 1 | 33 | 2.3 | 17 | 18 | 8.2 | 14.8 |
| 45 | 40 | 0.50 | Area 1+2 | 33 | 2.3 | 17 | 38 | 17.3 | 31.4 |
| 45 | 60 | 0.30 | Area 1 | 50 | 3.4 | 35 | 10 | 4.7 | 8.5 |
| 45 | 60 | 0.30 | Area 1+2 | 50 | 3.4 | 35 | 19 | 9.0 | 16.2 |
| 45 | 60 | 0.50 | Area 1 | 50 | 3.4 | 25 | 13 | 6.0 | 10.8 |
| 45 | 60 | 0.50 | Area 1+2 | 50 | 3.4 | 25 | 26 | 12.1 | 21.8 |
| 45 | 75 | 0.30 | Area 1 | 62 | 4.3 | 43 | 8 | 3.8 | 6.8 |
| 45 | 75 | 0.30 | Area 1+2 | 62 | 4.3 | 43 | 15 | 7.2 | 12.9 |
| 45 | 75 | 0.50 | Area 1 | 62 | 4.3 | 31 | 11 | 5.2 | 9.3 |
| 45 | 75 | 0.50 | Area 1+2 | 62 | 4.3 | 31 | 21 | 9.9 | 17.8 |

Reading: with a 45° lens, Area 1 only fits comfortably at 60–75 m with ≤ 50 % side overlap (~7–11 min);
Area 1 + 2 is 13–22 min — out of reach in a 30-min slot shared with three other missions unless the
airframe is fast and the endurance is long. GSD at 60–75 m is 3.4–4.3 cm/px: vehicle *type* is easy,
reading roof registration letters (~10 px tall) is doubtful → §5. Rerun with the real HFOV/speed/turn time.

## 4. Reuse from the SaR project — DONE 2026-09-08 (ported into `src/imav_m1/`, see ADR-006..009)
| SaR file | Reuse for | Notes |
|---|---|---|
| `sarFlightDay4/connection.py` | `src/imav_m1/vehicle/mavlink_vehicle.py` | Keeps the component-1 heartbeat filter — keep it |
| `sarFlightDay4/machine.py`, `states/` | `src/imav_m1/mission/state_machine.py` | Restructure states for survey → return → report |
| `sarFlightDay4/pattern_generator.py`, `waypoint_generator.py` | `src/imav_m1/mission/survey.py` | Lawnmower from polygon; add FOV/overlap-based spacing |
| `sarFlightDay4/kml_parser.py` | polygon input on the day | Draw the area in Mission Planner → KML → mission |
| `sarFlightDay4/config.py` | `config/*.yaml` | Converted to YAML profiles — no more editing Python to switch sim/real |
| `robin_package/vision.py` | `src/imav_m1/detection/detector.py` | Backends + undistortion. **The person model does not apply** (§5) |
| `robin_package/passive_watch.py` (GPS estimation) | `src/imav_m1/detection/georef.py` | GSD projection + tilt compensation. Extract only that |
| `robin_package/passive_watch.py` (`--fake` replay) | `imav-m1 replay` | Replay mode = camera-in-the-loop sim |
| `sarFlightDay4/gui.py` | `ops/dashboard.py` | Operator-only page (no spectator); the single START is the only in-mission action |
| `sarFlightDay4/cv_comm.py` | `detection/link.py` + `docs/DETECTION_INTERFACE.md` | Mode file kept; detections log added; placeholder detector process |

Operator sequence now: **Setup** (area → plan → fence + mission upload) → **Preflight** (checks + pilot-ready)
→ **START** → autonomous takeoff → survey → transit → NAV_LAND → results written → 5-min countdown.
Run it: `sim/README.md` (three terminals: SITL, Mission Planner bridge, `imav-m1 run`).

## 5. Identification strategy — decide by day 3 (needs an ADR)
The SaR detector finds people. Mission 1 needs vehicle **type** (CCF / VLTT / VT4 / GBC 180 / VBL) and, for
fire vehicles, the **brigade letters** on the roof. Options:
- **A. Onboard generic detector** (YOLOv8n COCO `car`/`truck` classes) → georef → type by a small classifier
  on the crop; brigade letters from the map by a human after landing. Autonomy factor for the human step
  is unclear (0.7? 0.4?) — ask.
- **B. Onboard detector + onboard OCR** on the roof crop. Text is ~10 px tall at 60 m: unlikely on a Pi 5 in time.
- **C. Two-pass**: survey high for the map, then a low (20–30 m) re-visit over each detection for a
  high-res crop → OCR or human. Costs flight time; reactive behaviour needs more testing.
- **D. Off-board**: dump images to the laptop after/during flight, detect + OCR there. A = 0.7 (−2.4 pts),
  far less risk, no Pi thermal/throughput worries.
Question for the organisers (mailing list / training day): is vehicle *type* alone worth partial points, or
are the brigade letters required? Does a human transcribing the table from an automatically produced map
count as off-board computation (0.7) or manual action (0.4)?

## 6. Simulation approach
- Vehicle: ArduPilot SITL (ArduCopter), started at the Haguenau field coordinates (`sim/locations.txt`,
  §5.2: 48.806567, 7.852134) so the lat/lon maths runs at the right latitude. Existing checkout at
  `~/Desktop/MSc Aerial Robotics/Group Project Assignment/SITL/ardupilot`; Docker fallback in `../sim/README.md`.
- GCS: Mission Planner in the Windows VM (existing) or MAVProxy `--map --console`.
- Camera: **no Gazebo** (ADR-005). Camera-in-the-loop = replay of recorded downward video through the real
  detector + synthetic vehicle chips pasted onto satellite tiles at the right GSD, with known coordinates,
  to measure georef error against the 5 m rule.
- Fence in SITL: load the §5.2 site polygon + a smaller flight area, `FENCE_ALT_MAX 75`, action LAND;
  Stage 2 of `SIM_TO_REAL.md` injects breaches.
- What SITL will NOT tell us: GPS/EKF noise, compass/vibration, wind, exposure at competition light, Pi
  thermal throttling under capture + inference. See the table in `SIM_TO_REAL.md`.

## 7. Open questions
- [ ] Airframe and all-up weight (< 5 kg, and W1 — see §2 item 5).
- [ ] Camera lens → HFOV. Any option for a second/zoom camera for roof text?
- [ ] Measured endurance vs the §3 table at the chosen altitude/speed.
- [ ] Radio: RC / telemetry / video at 2.4 or 5.8 GHz must be ≤ 25 mW (§2.1). Herelink and most SiK
  radios exceed that. What do we actually fly with, and what does the green-card check look at?
- [ ] Map deliverable format: rulebook only says "a map". Georeferenced mosaic PNG + KML overlay? Confirm
  on the training day.
- [ ] Map within 5 min of landing → pose-based quick mosaic (seconds) rather than ODM (too slow).
- [ ] Does arming / starting the mission from the GCS count as an in-mission manual action (A = 0.4)?
- [ ] Green card, AlphaTango, safety pilot — who, and by when?
- [ ] Area corners arrive on the day → what is the fastest trustworthy way to get them into config (KML from
  Mission Planner via `kml_parser.py`?). Rehearse it.

## 8. Proposed schedule (draft — adjust as §7 gets answered)
| Days | Focus | Exit criterion |
|---|---|---|
| 1–3 | ~~Port vehicle + state machine + survey; SITL end-to-end from Haguenau~~ **done day 1** (PROGRESS_LOG); ADR on identification | ~~`make mission-sim` flies Area 1 and lands~~ ✔ · time within budget: ≈ 8 sim-min at 60 m / 35 m spacing |
| 4–6 | Detection + georef in replay; synthetic-vehicle accuracy test; results table writer | georef error < 5 m with margin; Tab. 6 file produced automatically |
| 7–8 | Pose-tagged capture + quick mosaic; end-to-end "landing → deliverables in < 5 min" drill | judge-style dry run passes |
| 9–10 | Bench (props off) → hover → first survey flight | flight test cards filled |
| 11–12 | Full rehearsal ×2, fix, freeze (`comp-freeze` tag); precision landing only if spare time | frozen commit + params documented |
| 13 | Travel / pack / print checklists | preflight card printed; green-card paperwork ready |

## 9. Parking lot
- Live detection map on the GCS laptop (only if it costs no autonomy points).
- Adaptive re-visit of low-confidence detections (option C above).
- Missions 2–4 share the airframe and state machine; Mission 2 (two hot spots, GPS) is close to Mission 1.
