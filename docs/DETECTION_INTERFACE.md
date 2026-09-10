# Detector ↔ mission interface (for the detection / geotagging teammate)

The mission code (`imav-m1 run`) and the detector are **separate processes**. They share a run
directory and three files. No Python imports across the boundary; the detector may be any language.
This is the SaR `cv_comm.py` contract, extended with a detections log. Placeholder implementation:
`src/imav_m1/detection/placeholder.py` (run it to see the contract in action).

```
<run_dir>/                                  (data/flights/YYYY-MM-DD_<sim|hw>_NN_<name>/)
├── run.yaml                                commit, profile, merged config — read for camera params
├── telemetry.jsonl                         mission → detector, ~2–4 Hz, one JSON object per line
├── detections/
│   ├── cv_mode                             mission → detector: "PASSIVE" or "DETECTING"
│   └── detections.jsonl                    detector → mission: append one JSON object per detection
└── results/                                written by the mission on landing (uses detections.jsonl)
```

## What the mission guarantees
- `cv_mode` is replaced atomically (write-temp + rename). Missing file ⇒ treat as PASSIVE.
  `DETECTING` for the whole survey; `PASSIVE` on the ground, during takeoff, return, landing, abort.
- `telemetry.jsonl` lines (fields may be `null` before GPS lock):
  `{"t": 1788866000.123, "state": "SURVEY", "mode": "AUTO", "armed": true, "lat": 48.80, "lon": 7.85,
    "alt": 60.0, "hdg": 87.5, "gs": 9.8, "sats": 12, "fix": 3, "batt": 87, "wp": 7, "reached": 6}`
  `alt` is metres above home (GLOBAL_POSITION_INT.relative_alt), `hdg` degrees, `gs` m/s.
  The detector reads the last line (see `placeholder.py: last_pose`) or tails the file.
- The mission never blocks on the detector and never deletes `detections.jsonl` during a run.
- On landing, everything in `detections.jsonl` with a lat/lon becomes a row of the Tab. 6 table
  (`results/mission1_vehicles.csv`) and a marker on the map, so **only append what you would submit**
  (de-duplicate re-detections of the same vehicle on your side; use a stable `id`).

## What the detector must write — one line per detection, appended, `\n`-terminated
```json
{"t": 1788866012.4, "lat": 48.809512, "lon": 7.855101, "cls": "CCF", "ident": "67-CCF-M-ING",
 "conf": 0.87, "image": "detections/img_0012.jpg", "id": "veh-3", "source": "yolo"}
```
| field | required | meaning |
|---|---|---|
| `t` | yes | unix seconds of the frame |
| `lat`, `lon` | yes | georeferenced vehicle position, decimal degrees (rulebook: within 5 m) |
| `cls` | yes | `CCF` · `VLTT` · `VT4` · `GBC180` · `VBL` · `unknown` (rulebook §5.4.1) |
| `ident` | no | full identification if read, e.g. `67-CCF-M-ING` (brigade letters) or `GBC 180` |
| `conf` | no | 0–1 |
| `image` | no | path relative to the run dir; keep crops for the human check |
| `id` | yes | stable per vehicle so re-detections can be reconciled |
| `source` | no | `yolo`, `placeholder`, … |

The mission uses `ident` if present else `cls` as the "Vehicle Identification" column.

## Where to get camera / mission parameters
`run.yaml → config.camera` (model, width, height, hfov_deg, intrinsics_file, mount_yaw_offset_deg)
and `config.mission.cruise_alt_m`. On the aircraft the detector may also open its own MAVLink link to
the MAVProxy bridge (`udp:127.0.0.1:14551`, as the SaR `passive_watch.py` did) — the file stream is
simply the zero-dependency option and is what the placeholder uses.

## Running the placeholder against a SITL run
```bash
.venv/bin/imav-m1 run --profile sim --auto --no-gui          # starts the placeholder automatically
.venv/bin/python -m imav_m1.detection.placeholder --run-dir data/flights/<run> --targets '[...]'
```

---

## Starting your detector alongside the mission

You do not need to know the run directory in advance. The mission keeps a stable pointer to the
current run:

```
data/flights/latest  ->  data/flights/2026-09-10_sim_07_mission/
```

The launcher starts your process for you and passes it in:

```bash
scripts/launch_sim.sh --detector-cmd 'python3 /path/to/your_detector.py'
```

That opens a fourth Terminal window with two environment variables set:

| Variable | |
|---|---|
| `IMAV_RUN_DIR` | the run directory — `$IMAV_RUN_DIR/detections/cv_mode` and `$IMAV_RUN_DIR/telemetry.jsonl` |
| `IMAV_DASHBOARD` | base URL of the operator dashboard, for the HTTP option below |

On the aircraft the same thing happens through `./scripts/launch_hardware.sh --detector-cmd '…'`.

## Two equally supported ways to report a detection

**A. Append a line to the file** (no dependencies, works if the dashboard is off):

```python
import json, os
with open(os.path.join(os.environ["IMAV_RUN_DIR"], "detections/detections.jsonl"), "a") as f:
    f.write(json.dumps({"t": 1789050000.0, "lat": 48.8095202, "lon": 7.8520274,
                        "cls": "CCF", "ident": "67-CCF-M-ING", "conf": 0.87, "id": "veh-3"}) + "\n")
    f.flush()
```

**B. POST it to the mission** — same fields, same result:

```bash
curl -X POST "$IMAV_DASHBOARD/api/detection" -H 'content-type: application/json' \
     -d '{"lat":48.8095202,"lon":7.8520274,"cls":"CCF","ident":"67-CCF-M-ING","id":"veh-3"}'
```

`lat`, `lon` and `cls` are required; `t` and `source` are filled in for you. The endpoint appends to
the very same file, so the dashboard list, the vehicle table and the map behave identically either
way. Pick whichever suits your code; you can mix them.

## What we do not need to know

How you capture frames, which model you run, how you georeference, or what you do on the Pi. The
mission only ever reads `detections.jsonl`. Anything with a `lat`, `lon` and `cls` ends up in the
submission table, so de-duplicate on your side and only append what you would submit.
