# hardware/
- `params/`      — ArduPilot full parameter dumps, one per change: `YYYY-MM-DD_<airframe>_<fw>.param`.
                   Dump from Mission Planner (Full Parameter List → Save) or MAVProxy `param download`.
                   Record sha256 in `docs/HARDWARE.md`. Never edit these by hand.
- `calibration/` — camera intrinsics (`imx296_intrinsics.yaw`: fx, fy, cx, cy, dist coeffs, image size),
                   plus the checkerboard images used. Re-run if the lens or mount changes.
- photos of wiring / mounts (annotated) — worth their weight in the field.
