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
