#!/usr/bin/env bash
# Run the mission from a terminal.  Usage: scripts/run_mission.sh sim [extra imav-m1 flags]
#                                         scripts/run_mission.sh hardware
# sim: expects SITL running (scripts/start_sitl.sh).  hardware (on the Pi): runs preflight, starts the
# MAVProxy bridge (as SaR main.py did), then the mission code.  Env GCS_HOST for the hardware bridge.
set -euo pipefail
PROFILE="${1:?usage: run_mission.sh <sim|hardware> [flags]}"; shift || true
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
PY="$HERE/.venv/bin/python"; [ -x "$PY" ] || PY=python3

if [ "$PROFILE" = "hardware" ]; then
  ./scripts/preflight.sh
  GCS_HOST="${GCS_HOST:-ROBINCARTERC2F9.local}"
  if ! pgrep -f "mavproxy.py --master=/dev/ttyAMA0" >/dev/null; then
    echo "starting MAVProxy bridge: /dev/ttyAMA0 -> udp:$GCS_HOST:14550 + udp:127.0.0.1:14551"
    mavproxy.py --master=/dev/ttyAMA0,921600 --out="udp:$GCS_HOST:14550" --out=udp:127.0.0.1:14551 \
      --daemon --non-interactive --state-basedir=/tmp > /tmp/mavproxy_bridge.log 2>&1 &
    sleep 3
  fi
fi
exec "$PY" -m imav_m1.cli run --profile "$PROFILE" "$@"
