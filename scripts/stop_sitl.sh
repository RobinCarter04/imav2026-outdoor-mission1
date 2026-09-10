#!/usr/bin/env bash
# Stop the SITL started by start_sitl.sh (and any stray arducopter SITL).
HERE="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$HERE/sim/runtime/sitl.pid" ] && kill "$(cat "$HERE/sim/runtime/sitl.pid")" 2>/dev/null && rm -f "$HERE/sim/runtime/sitl.pid"
pkill -f "build/sitl/bin/arducopter" 2>/dev/null
sleep 0.5; pgrep -fl "build/sitl/bin/arducopter" >/dev/null && echo "still running" || echo "SITL stopped"
