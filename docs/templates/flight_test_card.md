# Flight test card

| Field | Value |
|---|---|
| Test ID | FT-YYYY-MM-DD-NN |
| Date / time / location | |
| Crew (pilot / GCS operator / observer) | |
| Weather (wind, light, temp) | |
| Aircraft / battery ID / voltage at start | |
| Firmware / param file hash | (from `docs/HARDWARE.md`) |
| Mission code commit / profile | `abc1234` / hardware |
| SIM_TO_REAL stage | 3 / 4 / 5 |

## Objective (one sentence)

## Pass criteria (measurable)
1.
2.

## Procedure
1.
2.

## Pre-flight (tick)
- [ ] `scripts/preflight.sh` passed on the Pi
- [ ] Fence polygon loaded and enabled; RTL altitude set
- [ ] RC failsafe verified (TX off → failsafe triggers) on the bench
- [ ] Safety pilot briefed on take-over switch and abort criteria
- [ ] Area clear; observers positioned
- [ ] Log folder created: `data/flights/YYYY-MM-DD_hw_NN_<desc>/`

## Result
PASS / FAIL / PARTIAL — evidence:

## Anomalies / surprises

## Logs collected
- [ ] `.BIN` dataflash  - [ ] `.tlog`  - [ ] `mission.log`  - [ ] images/detections  - [ ] `run.yaml`

## Follow-ups (→ PROGRESS_LOG / issues)
