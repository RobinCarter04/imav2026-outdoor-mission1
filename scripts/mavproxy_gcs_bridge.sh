#!/usr/bin/env bash
# Optional: forward SITL SERIAL0 (5760) to a ground station, e.g. Mission Planner in the Parallels VM.
# Usage: scripts/mavproxy_gcs_bridge.sh <GCS_HOST_OR_IP> [port=14550]
# (Alternatively point Mission Planner straight at TCP <this Mac's IP>:5763 — SITL SERIAL2.)
set -euo pipefail
GCS="${1:?usage: mavproxy_gcs_bridge.sh <gcs-host> [port]}"; PORT="${2:-14550}"
exec mavproxy.py --master=tcp:127.0.0.1:5760 --out="udp:$GCS:$PORT" --daemon --non-interactive
