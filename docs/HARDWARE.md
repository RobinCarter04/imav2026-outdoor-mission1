# Hardware

Single source of truth for what is on the aircraft and which versions are flying. Update this the
same day anything changes. Values marked *(SaR)* were carried over from the SaR project — **confirm**.

## Aircraft
| Item | Value | Confirmed? |
|---|---|---|
| Airframe | Hexsoon EDU-450 **hexacopter** *(SaR HITL guide)* — SITL frame `hexa` | ☐ |
| All-up weight (with battery, camera, Pi) | TBD kg — MTOW 5 kg (§2); mass factor rewards light: 2 kg → ×1.66, 3 kg → ×1.39 (Tab. 7) | ☐ |
| Dimensions | TBD | ☐ |
| Autopilot | CubePilot Cube Orange+ *(SaR HITL guide)* | ☐ |
| Firmware | ArduCopter TBD — record exact version string from `AUTOPILOT_VERSION` | ☐ |
| GPS | Here 3+ *(SaR HITL guide)* | ☐ |
| Telemetry to GCS | TBD — power limits §2.1: 2.4 / 5.8 GHz ≤ 25 mW, 868 MHz ≤ 25 mW, 433 MHz ≤ 10 mW. Check Herelink / SiK output | ☐ |
| RC | FrSky Twin X14 / TW-Mini *(SaR HITL guide)* — failsafe verified, **kill switch on the transmitter is mandatory (§2)** | ☐ |
| Battery | TBD (capacity, cells, measured endurance) | ☐ |

## Companion computer
| Item | Value | Confirmed? |
|---|---|---|
| Board | Raspberry Pi 5 *(SaR)* | ☐ |
| OS / Python | Raspberry Pi OS, Python 3.13 *(SaR README)* | ☐ |
| Link to autopilot | UART `/dev/ttyAMA0` @ 921600 → Cube TELEM port *(SaR config.py)* | ☐ |
| MAVProxy bridge | master `/dev/ttyAMA0`, outputs `udp:<GCS>:14550` (GCS) and `udp:127.0.0.1:14551` (mission code) *(SaR)* | ☐ |
| Power | TBD (BEC rating — Pi 5 wants 5 V / 5 A under load) | ☐ |
| Cooling | TBD — Pi 5 throttles; active cooler? | ☐ |

## Camera
| Item | Value | Confirmed? |
|---|---|---|
| Sensor | IMX296 global shutter, 1456×1088 *(SaR)* | ☐ |
| Lens / HFOV | TBD — from calibration; drives coverage time and GSD (`tools/coverage_calc.py`) | ☐ |
| Mount | downward, rigid, yaw offset TBD | ☐ |
| Intrinsics file | `hardware/calibration/imx296_intrinsics.yaml` (TODO: re-calibrate) | ☐ |
| GSD at mission altitude | TBD cm/px — vehicle type needs ~20 px across a vehicle; roof registration letters need far more | ☐ |

## Pinned versions (update on every change, reference in PROGRESS_LOG)
| What | Version / hash | Date |
|---|---|---|
| ArduCopter firmware | TBD | |
| Param file | `hardware/params/<file>.param` sha256 TBD | |
| Mission code | git tag `comp-freeze` (to create) | |
| Detector weights | see `data/models/MANIFEST.md` | |
| Pi Python deps | `pip freeze > hardware/pi_requirements_lock.txt` on the Pi | |

## Wiring / photos
Put annotated photos of the wiring and camera mount in `hardware/` — they save an hour in the field.
