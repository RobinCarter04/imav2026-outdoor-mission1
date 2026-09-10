#!/usr/bin/env bash
# Stop everything scripts/launch_sim.sh started: SITL, the MAVProxy GCS bridge, the mission process.
# The Terminal windows stay open showing their final output; close them when you have read it.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"

found=0
for pat in "build/sitl/bin/arducopter" "mavproxy" "imav_m1.cli run" "imav_m1.detection.placeholder"; do
  pids=$(pgrep -f "$pat" || true)
  [ -z "$pids" ] && continue
  found=1
  echo "stopping: $pat  (pids: $pids)"
  kill $pids 2>/dev/null || true
done
[ "$found" = "0" ] && { echo "nothing running"; exit 0; }
sleep 2
for pat in "build/sitl/bin/arducopter" "mavproxy" "imav_m1.cli run" "imav_m1.detection.placeholder"; do
  pids=$(pgrep -f "$pat" || true)
  [ -n "$pids" ] && { echo "force-stopping $pat"; kill -9 $pids 2>/dev/null || true; }
done
rm -f "$HERE"/sim/runtime/sitl.pid "$HERE"/sim/runtime/i*/sitl.pid 2>/dev/null
sleep 1
remaining=$(pgrep -fl "arducopter|mavproxy|imav_m1" || true)
[ -z "$remaining" ] && echo "all stopped" || { echo "still running:"; echo "$remaining" | cut -c1-100; }
