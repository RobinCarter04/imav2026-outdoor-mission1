#!/usr/bin/env bash
# One command to bring up a flight session ON THE AIRCRAFT'S Raspberry Pi.
#
#   ./scripts/launch_hardware.sh --gcs 192.168.1.50     full flight session (preflight gate first)
#   ./scripts/launch_hardware.sh --site fenswood --gcs …  fly the Fenswood test areas
#   ./scripts/launch_hardware.sh --bench                bench bring-up, props OFF, NOT cleared to fly
#   ./scripts/launch_hardware.sh --stop                 stop everything
#   tmux attach -t imav                                 re-attach after the SSH link drops
#
# Everything runs inside a tmux session so a dropped SSH connection NEVER kills the mission:
#   window 0  bridge     MAVProxy: /dev/ttyAMA0 -> udp:<gcs>:14550 (Mission Planner) + udp:127.0.0.1:14551
#   window 1  mission    imav-m1 run --profile hardware   dashboard on http://<pi>:5000
#   window 2  detector   the detection process (--detector-cmd, default: placeholder, none = skip)
#
# This script never arms anything. The aircraft only moves after a human presses START in the
# dashboard, with the safety pilot on the sticks (docs/SAFETY.md).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
SESSION="imav"
GCS="${GCS_HOST:-}"; BENCH=0; STOP=0; DETACH=0; DRY=0; KML=""; NAME="flight"; SITE=""
DETECTOR_CMD=""; SERIAL="${MAVLINK_SERIAL:-/dev/ttyAMA0}"; BAUD="${MAVLINK_BAUD:-921600}"

while [ $# -gt 0 ]; do
  case "$1" in
    --gcs)          GCS="${2:?--gcs needs the ground station IP}"; shift 2 ;;
    --kml)          KML="${2:?}"; shift 2 ;;
    --site)         SITE="${2:?--site needs a site name}"; shift 2 ;;
    --name)         NAME="${2:?}"; shift 2 ;;
    --detector-cmd) DETECTOR_CMD="${2:?}"; shift 2 ;;
    --serial)       SERIAL="${2:?}"; shift 2 ;;
    --bench)        BENCH=1; shift ;;
    --detach)       DETACH=1; shift ;;
    --stop)         STOP=1; shift ;;
    --dry-run)      DRY=1; shift ;;
    -h|--help)      sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown option: $1  (--help for usage)" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
have_tmux() { command -v tmux >/dev/null 2>&1; }

if [ "$STOP" = "1" ]; then
  have_tmux && tmux kill-session -t "$SESSION" 2>/dev/null && say "tmux session '$SESSION' killed"
  for pat in "imav_m1.cli run" "imav_m1.detection" "mavproxy"; do
    pids=$(pgrep -f "$pat" || true); [ -n "$pids" ] && { echo "stopping $pat ($pids)"; kill $pids 2>/dev/null || true; }
  done
  sleep 2; pgrep -fl "imav_m1|mavproxy" || say "all stopped"; exit 0
fi

# ── preconditions ───────────────────────────────────────────────────────────────────────────
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || die "no virtualenv on this machine — run: make setup"
"$PY" -c "import imav_m1" 2>/dev/null || die "imav_m1 not installed — run: make setup"
[ -e "$SERIAL" ] || warn "$SERIAL not present — are you on the Pi? (override with --serial)"
[ -z "$KML" ] || [ -f "$KML" ] || die "KML not found: $KML"
[ -n "$GCS" ] || warn "no --gcs given: Mission Planner will not receive telemetry from this run"
if pgrep -f "imav_m1.cli run" >/dev/null; then die "a mission is already running — ./scripts/launch_hardware.sh --stop first"; fi

# ── safety gate ─────────────────────────────────────────────────────────────────────────────
if [ "$BENCH" = "1" ]; then
  warn "BENCH MODE — props OFF. This run is NOT cleared for flight: the preflight gate is skipped."
  warn "Do not fly from a bench-mode session (docs/SIM_TO_REAL.md stage 3)."
else
  say "running the flight preflight checks (docs/SIM_TO_REAL.md)"
  ./scripts/preflight.sh || die "preflight FAILED — do not fly. Fix the items above, or use --bench for ground testing."
fi

MISSION_ARGS="run --profile hardware --name $NAME"
[ -z "$SITE" ] || MISSION_ARGS="$MISSION_ARGS --site $SITE"
[ -z "$KML" ] || MISSION_ARGS="$MISSION_ARGS --kml $KML"
[ -n "$DETECTOR_CMD" ] || DETECTOR_CMD="skip"   # the mission starts its own placeholder unless told otherwise
[ "$DETECTOR_CMD" = "skip" ] || MISSION_ARGS="$MISSION_ARGS --detector none"

BRIDGE_CMD="mavproxy.py --master=$SERIAL,$BAUD --out=udp:127.0.0.1:14551 --non-interactive --state-basedir=/tmp"
[ -z "$GCS" ] || BRIDGE_CMD="$BRIDGE_CMD --out=udp:$GCS:14550"
MISSION_CMD=".venv/bin/imav-m1 $MISSION_ARGS"

if [ "$DRY" = "1" ]; then
  echo "would run, in tmux session '$SESSION':"
  echo "    bridge:   $BRIDGE_CMD"
  echo "    mission:  $MISSION_CMD"
  [ "$DETECTOR_CMD" = "skip" ] && echo "    detector: (started by the mission process)" || echo "    detector: $DETECTOR_CMD"
  exit 0
fi

# ── bring it up ─────────────────────────────────────────────────────────────────────────────
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}'); PI_IP="${PI_IP:-$(hostname)}"
if have_tmux; then
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  say "1/3  MAVLink bridge on $SERIAL @ $BAUD"
  tmux new-session -d -s "$SESSION" -n bridge -c "$HERE" "$BRIDGE_CMD; echo; echo '[bridge exited — press Enter]'; read _"
  sleep 4
  say "2/3  mission (dashboard: http://$PI_IP:5000/)"
  tmux new-window -t "$SESSION" -n mission -c "$HERE" "$MISSION_CMD; echo; echo '[mission exited — press Enter]'; read _"
  if [ "$DETECTOR_CMD" != "skip" ]; then
    sleep 2; say "3/3  detector: $DETECTOR_CMD"
    tmux new-window -t "$SESSION" -n detector -c "$HERE" "$DETECTOR_CMD; echo; echo '[detector exited — press Enter]'; read _"
  else
    say "3/3  detector started by the mission process"
  fi
else
  warn "tmux is not installed (sudo apt install tmux) — falling back to background processes + log files"
  mkdir -p "$HERE/sim/runtime"
  setsid nohup bash -c "$BRIDGE_CMD"  > "$HERE/sim/runtime/bridge.log"  2>&1 < /dev/null &
  sleep 4
  setsid nohup bash -c "$MISSION_CMD" > "$HERE/sim/runtime/mission.log" 2>&1 < /dev/null &
  [ "$DETECTOR_CMD" = "skip" ] || setsid nohup bash -c "$DETECTOR_CMD" > "$HERE/sim/runtime/detector.log" 2>&1 < /dev/null &
  sleep 3
fi

cat <<TXT

    dashboard        http://$PI_IP:5000/     ← open this on the ground-station laptop
    Mission Planner  ${GCS:+UDP 14550 at $GCS}${GCS:-not bridged (no --gcs)}
    results          data/flights/<today>_hw_NN_$NAME/
    reattach         tmux attach -t $SESSION        (safe after the SSH link drops)
    stop everything  ./scripts/launch_hardware.sh --stop

    The aircraft will not move until a human presses START in the dashboard.
    Safety pilot on the sticks, kill switch checked, before anyone touches that button.
TXT

if have_tmux && [ "$DETACH" = "0" ]; then
  say "attaching to tmux (Ctrl-B then D to detach and leave everything running)"
  sleep 2; exec tmux attach -t "$SESSION"
fi
