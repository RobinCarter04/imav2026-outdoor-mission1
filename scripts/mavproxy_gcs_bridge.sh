#!/usr/bin/env bash
# Optional: forward SITL SERIAL0 (5760) to a ground station, e.g. Mission Planner in the Parallels VM.
# Usage: scripts/mavproxy_gcs_bridge.sh <GCS_HOST_OR_IP> [udp_port=14550] [sitl_gcs_port=5760]
# (Alternatively point Mission Planner straight at TCP <this Mac's IP>:5763 — SITL SERIAL2.)
set -euo pipefail
GCS="${1:?usage: mavproxy_gcs_bridge.sh <gcs-host> [udp_port] [sitl_gcs_port]}"; PORT="${2:-14550}"; SITL_PORT="${3:-5760}"
echo "bridging SITL tcp:127.0.0.1:$SITL_PORT  ->  udp:$GCS:$PORT   (Mission Planner: UDP, port $PORT)"
exec mavproxy.py --master="tcp:127.0.0.1:$SITL_PORT" --out="udp:$GCS:$PORT" --non-interactive
