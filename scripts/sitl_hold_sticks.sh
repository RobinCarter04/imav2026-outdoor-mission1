#!/usr/bin/env bash
# Hold the SIMULATED RC sticks centred, with throttle at mid.
#
#   scripts/sitl_hold_sticks.sh [port=5763]        Ctrl-C to release
#
# Why this exists: raw SITL (no MAVProxy console) starts with the simulated throttle stick at its
# MINIMUM. Modes that follow the pilot's throttle — LOITER, ALT_HOLD, POSHOLD — therefore command a
# full descent the moment you select them, and the aircraft lands and disarms. That is a property of
# the simulator's fake RC, not of the aircraft or the mission code.
#
# Run this in a spare window before taking over with LOITER from Mission Planner, and the aircraft
# holds altitude like a real one with a pilot holding mid-stick. GUIDED and BRAKE ignore the sticks,
# so they need no help.
set -euo pipefail
PORT="${1:-5763}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$HERE/.venv/bin/python"; [ -x "$PY" ] || PY=python3
echo "holding simulated sticks centred on tcp:127.0.0.1:$PORT (Ctrl-C to release)"
exec "$PY" - "$PORT" <<'PY'
import sys, time
from pymavlink import mavutil
m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{sys.argv[1]}", source_system=251)
m.wait_heartbeat(timeout=30)
print("connected — roll/pitch/yaw centred, throttle mid (1500)")
try:
    while True:
        m.mav.rc_channels_override_send(m.target_system, m.target_component,
                                        1500, 1500, 1500, 1500, 0, 0, 0, 0)
        time.sleep(0.5)
except KeyboardInterrupt:
    m.mav.rc_channels_override_send(m.target_system, m.target_component, *([0] * 8))
    print("\nreleased")
PY
