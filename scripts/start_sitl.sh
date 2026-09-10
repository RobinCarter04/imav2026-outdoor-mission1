#!/usr/bin/env bash
# Start ArduCopter SITL (hexa, Haguenau) by running the prebuilt binary directly — headless, no
# MAVProxy, no Terminal window. SERIAL0 is started in no-wait mode so boot never blocks on a GCS. Ports: 5760 SERIAL0 (GCS/MAVProxy), 5762 SERIAL1 (mission code,
# config/sim.yaml), 5763 SERIAL2 (spare, e.g. Mission Planner in the VM via TCP).
# Usage: scripts/start_sitl.sh         background (log: sim/runtime/sitl.log, stop: scripts/stop_sitl.sh)
#        scripts/start_sitl.sh --fg    foreground in this terminal, Ctrl-C to stop (recommended for terminal 1)
# Env: ARDUPILOT_DIR (checkout with build/sitl/bin/arducopter), SITL_LOC="lat,lon,alt,hdg",
#      FRAME (default hexa), SPEEDUP (default 1), WIPE=1 to reset eeprom (params) on start.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_AP="$HOME/Desktop/MSc Aerial Robotics/Group Project Assignment/SITL/ardupilot"
ARDUPILOT_DIR="${ARDUPILOT_DIR:-$DEFAULT_AP}"
BIN="$ARDUPILOT_DIR/build/sitl/bin/arducopter"
FRAME="${FRAME:-hexa}"
SPEEDUP="${SPEEDUP:-1}"
SITL_LOC="${SITL_LOC:-$(grep '^IMAV2026=' "$HERE/sim/locations.txt" | cut -d= -f2)}"
RT="$HERE/sim/runtime"; mkdir -p "$RT"

[ -x "$BIN" ] || { echo "arducopter SITL binary not found at $BIN — build it or set ARDUPILOT_DIR (sim/README.md)" >&2; exit 1; }
if pgrep -f "build/sitl/bin/arducopter" >/dev/null; then echo "SITL already running (scripts/stop_sitl.sh to stop)"; exit 0; fi

DEF="$ARDUPILOT_DIR/Tools/autotest/default_params/copter.parm"
[ -f "$ARDUPILOT_DIR/Tools/autotest/default_params/copter-$FRAME.parm" ] && DEF="$DEF,$ARDUPILOT_DIR/Tools/autotest/default_params/copter-$FRAME.parm"
[ -f "$HERE/sim/sitl_params.parm" ] && DEF="$DEF,$HERE/sim/sitl_params.parm"
WIPE_ARG=""; [ "${WIPE:-0}" = "1" ] && WIPE_ARG="-w"
[ -f "$RT/eeprom.bin" ] || WIPE_ARG="-w"

cd "$RT"
echo "Starting SITL: frame=$FRAME home=$SITL_LOC speedup=$SPEEDUP ${WIPE_ARG:+(wiping eeprom)}"
if [ "${1:-}" = "--fg" ]; then
  echo "foreground mode — mission code: tcp:127.0.0.1:5762, GCS: 5760 / 5763. Ctrl-C stops SITL."
  exec "$BIN" $WIPE_ARG --model "$FRAME" --speedup "$SPEEDUP" --home "$SITL_LOC" --defaults "$DEF" --serial0 tcp:0:nowait
fi
nohup "$BIN" $WIPE_ARG --model "$FRAME" --speedup "$SPEEDUP" --home "$SITL_LOC" --defaults "$DEF" --serial0 tcp:0:nowait > "$RT/sitl.log" 2>&1 &
echo $! > "$RT/sitl.pid"
for i in $(seq 1 30); do
  if grep -q "SERIAL1 on TCP port 5762" "$RT/sitl.log" 2>/dev/null; then
    echo "SITL up (pid $(cat "$RT/sitl.pid")). Mission code: tcp:127.0.0.1:5762. Log: sim/runtime/sitl.log"; exit 0
  fi
  sleep 0.5
done
echo "SITL did not report SERIAL1 within 15 s — see $RT/sitl.log" >&2; exit 1
