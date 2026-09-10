#!/usr/bin/env bash
# One command to bring up a full simulation session on this Mac.
#
#   scripts/launch_sim.sh                        SITL + mission dashboard (2 windows)
#   scripts/launch_sim.sh --gcs 10.211.55.3      + MAVProxy bridge for Mission Planner (3 windows)
#   scripts/launch_sim.sh --auto                 scripted mission, no clicking, window closes when done
#   scripts/launch_sim.sh --site fenswood        fly the Fenswood (SaR) areas instead of IMAV
#   scripts/launch_sim.sh --detector-cmd 'python my_detector.py'    start a teammate's detector too
#   scripts/launch_sim.sh --kml sim/areas/haguenau_fig19.kml --speedup 5
#
# Each stage gets its own Terminal window, opened only once the previous stage is actually ready:
#   1  SITL          scripts/start_sitl.sh --fg      Ctrl-C in that window stops the simulator
#   2  GCS bridge    scripts/mavproxy_gcs_bridge.sh  (only with --gcs)
#   3  Mission       imav-m1 run --profile sim       operator dashboard at http://localhost:PORT
#
# Stop everything with scripts/stop_sim.sh (or Ctrl-C each window).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

GCS=""; AUTO=0; KML=""; SITE=""; DETECTOR_CMD=""
SPEEDUP="${SPEEDUP:-1}"; INSTANCE="${INSTANCE:-0}"; WIPE="${WIPE:-0}"
NO_MISSION=0; CLEAN=0; DRY=0; BROWSER=1; SETTLE="${SETTLE:-25}"; NAME="mission"; DETECTOR="placeholder"
SITE="${SITE:-}"; DETECTOR_CMD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --gcs)        GCS="${2:?--gcs needs a host or IP}"; shift 2 ;;
    --auto)       AUTO=1; shift ;;
    --kml)        KML="${2:?--kml needs a file}"; shift 2 ;;
    --speedup)    SPEEDUP="${2:?}"; shift 2 ;;
    --instance)   INSTANCE="${2:?}"; shift 2 ;;
    --name)       NAME="${2:?}"; shift 2 ;;
    --detector)   DETECTOR="${2:?}"; shift 2 ;;
    --site)       SITE="${2:?--site needs a name, e.g. imav or fenswood}"; shift 2 ;;
    --detector-cmd) DETECTOR_CMD="${2:?}"; DETECTOR="none"; shift 2 ;;
    --settle)     SETTLE="${2:?}"; shift 2 ;;
    --wipe)       WIPE=1; shift ;;
    --no-mission) NO_MISSION=1; shift ;;
    --no-browser) BROWSER=0; shift ;;
    --clean)      CLEAN=1; shift ;;
    --dry-run)    DRY=1; shift ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1  (--help for usage)" >&2; exit 2 ;;
  esac
done

SERIAL0=$((5760 + 10 * INSTANCE))
SERIAL1=$((5762 + 10 * INSTANCE))
DASH_PORT=$((5000 + INSTANCE))
LAUNCH_DIR="$HERE/sim/runtime/launch"
PY="$HERE/.venv/bin/python"

say()  { printf '\033[1m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── preconditions ───────────────────────────────────────────────────────────────────────────
[ -x "$PY" ] || die "no virtualenv — run: make setup"
"$PY" -c "import imav_m1" 2>/dev/null || die "imav_m1 not installed in .venv — run: make setup"
[ -z "$KML" ] || [ -f "$KML" ] || die "KML not found: $KML"

# The site decides where SITL starts, so the simulated aircraft boots on the right field.
SITE_ARG=""; [ -z "$SITE" ] || SITE_ARG="--site $SITE"
SITE_HOME=$("$PY" - "$SITE" <<'EOP' 2>/dev/null || true
import sys
from imav_m1.config import load_config
cfg = load_config("sim", sys.argv[1] or None)
home = (cfg.get("site") or {}).get("sitl_home")
print(",".join(str(v) for v in home) if home else "")
print((cfg.get("site") or {}).get("name") or "")
EOP
)
SITE_NAME=$(echo "$SITE_HOME" | sed -n 2p); SITE_HOME=$(echo "$SITE_HOME" | sed -n 1p)
[ -n "$SITE_NAME" ] || die "could not load site '${SITE:-default}' — try: .venv/bin/imav-m1 check-config --profile sim --site $SITE"
[ -n "$SITE_HOME" ] || warn "site '$SITE_NAME' has no sitl_home — SITL will use sim/locations.txt"
[ -z "$SITE_HOME" ] || say "site $SITE_NAME: SITL home $SITE_HOME"

STRAY_SITL=$(pgrep -f "build/sitl/bin/arducopter" || true)
STRAY_PROXY=$(pgrep -f "mavproxy" || true)
STRAY_MISSION=$(pgrep -f "imav_m1.cli run" || true)
STRAYS="$STRAY_SITL $STRAY_PROXY $STRAY_MISSION"
if [ -n "${STRAYS// /}" ]; then
  if [ "$CLEAN" = "1" ]; then
    say "cleaning up existing SITL / MAVProxy / mission processes"
    [ "$DRY" = "1" ] || { kill $STRAYS 2>/dev/null || true; sleep 2; kill -9 $STRAYS 2>/dev/null || true; }
  else
    warn "these are already running:"
    ps -o pid,etime,command -p $STRAYS 2>/dev/null | tail -n +2 | cut -c1-110 | sed 's/^/    /'
    warn "an idle MAVProxy left on SITL's GCS port FREEZES the simulator — clear it first."
    [ "$DRY" = "1" ] || die "re-run with --clean to stop them, or stop them yourself (scripts/stop_sim.sh)"
  fi
fi
for p in "$SERIAL0" "$SERIAL1"; do
  if nc -z 127.0.0.1 "$p" 2>/dev/null; then
    warn "port $p is already in use"
    [ "$DRY" = "1" ] || die "try --instance 1, or scripts/stop_sim.sh"
  fi
done

# ── window helper: run a command in its own Terminal window ─────────────────────────────────
mkdir -p "$LAUNCH_DIR"
open_window() {   # open_window <slug> <title> <command...>
  local slug="$1" title="$2"; shift 2
  local f="$LAUNCH_DIR/${slug}.command"
  {
    echo '#!/bin/bash'
    echo "printf '\\033]0;$title\\007'"
    echo "cd '$HERE' || exit 1"
    echo "echo '── $title ──'"
    printf '%s\n' "$*"
    echo 'status=$?'
    echo 'echo; echo "[$0 exited with status $status — close this window or press Enter]"; read -r _'
  } > "$f"
  chmod +x "$f"
  if [ "$DRY" = "1" ]; then echo "    would open: $title"; sed 's/^/        /' "$f" | sed -n '4,6p'; return; fi
  open -a Terminal "$f"
}

wait_port() {     # wait_port <port> <seconds> <what>
  local port="$1" limit="$2" what="$3" i=0
  while [ "$i" -lt "$limit" ]; do
    nc -z 127.0.0.1 "$port" 2>/dev/null && { say "$what ready on port $port"; return 0; }
    sleep 1; i=$((i + 1)); printf '.'
  done
  echo; return 1
}

# ── 1. SITL ─────────────────────────────────────────────────────────────────────────────────
say "1/3  starting ArduCopter SITL at $SITE_NAME (instance $INSTANCE, speedup ${SPEEDUP}x)"
open_window "1_sitl" "SITL  $SITE_NAME" \
  "SPEEDUP=$SPEEDUP INSTANCE=$INSTANCE WIPE=$WIPE ${SITE_HOME:+SITL_LOC=$SITE_HOME} ./scripts/start_sitl.sh --fg"
if [ "$DRY" = "0" ]; then
  printf '     waiting for SITL '
  wait_port "$SERIAL1" 60 "SITL" || die "SITL did not open port $SERIAL1 — see its window and sim/runtime/sitl.log"
fi

# ── 2. GCS bridge (optional) ────────────────────────────────────────────────────────────────
if [ -n "$GCS" ]; then
  say "2/3  bridging SITL to Mission Planner at $GCS (UDP 14550)"
  open_window "2_gcs" "GCS bridge → $GCS" "./scripts/mavproxy_gcs_bridge.sh '$GCS' 14550 $SERIAL0"
  [ "$DRY" = "1" ] || sleep 3
else
  say "2/3  no --gcs given, skipping the Mission Planner bridge"
  say "     (to spectate later: scripts/mavproxy_gcs_bridge.sh <vm-host-or-ip> 14550 $SERIAL0,"
  say "      or point Mission Planner at TCP <this Mac>:$((SERIAL0 + 3)))"
fi

# ── 3. mission ──────────────────────────────────────────────────────────────────────────────
if [ "$NO_MISSION" = "1" ]; then
  say "3/3  --no-mission: start it yourself with"
  echo "        .venv/bin/imav-m1 run --profile sim --connection tcp:127.0.0.1:$SERIAL1"
else
  if [ "$DRY" = "0" ] && [ "$SETTLE" -gt 0 ]; then
    printf '     letting GPS/EKF settle (%ss) ' "$SETTLE"
    for _ in $(seq 1 "$SETTLE"); do sleep 1; printf '.'; done; echo
  fi
  MISSION_ARGS="run --profile sim $SITE_ARG --connection tcp:127.0.0.1:$SERIAL1 --name $NAME --detector $DETECTOR --port $DASH_PORT"
  [ -z "$KML" ] || MISSION_ARGS="$MISSION_ARGS --kml '$KML'"
  [ "$AUTO" = "0" ] || MISSION_ARGS="$MISSION_ARGS --auto --no-gui"
  say "3/3  starting the mission at $SITE_NAME"
  open_window "3_mission" "Mission  $SITE_NAME" ".venv/bin/imav-m1 $MISSION_ARGS"
  if [ -n "$DETECTOR_CMD" ]; then
    # The teammate's detector, started as its own process. It finds the run through the stable
    # data/flights/latest pointer (docs/DETECTION_INTERFACE.md); the mission never waits for it.
    say "4/4  detector: $DETECTOR_CMD"
    if [ "$DRY" = "0" ]; then
      for _ in $(seq 1 40); do [ -e "$HERE/data/flights/latest" ] && break; sleep 0.5; done
    fi
    open_window "4_detector" "Detector" \
      "IMAV_RUN_DIR='$HERE/data/flights/latest' IMAV_DASHBOARD='http://127.0.0.1:$DASH_PORT' $DETECTOR_CMD"
  fi
  if [ "$AUTO" = "0" ] && [ "$BROWSER" = "1" ] && [ "$DRY" = "0" ]; then
    sleep 4; open "http://localhost:$DASH_PORT/" 2>/dev/null || true
  fi
fi

if [ -n "$GCS" ]; then MP="UDP port 14550 (bridge running to $GCS)"; else MP="TCP <this Mac>:$((SERIAL0 + 3))"; fi
if [ "$AUTO" = "1" ]; then DASH="(skipped: --auto writes the results and exits)"; else DASH="http://localhost:$DASH_PORT/"; fi
echo
say "up and running"
cat <<TXT
    site             $SITE_NAME${SITE_HOME:+  (home $SITE_HOME)}
    SITL             tcp:127.0.0.1:$SERIAL1 for the mission; $SERIAL0 / $((SERIAL0 + 3)) for ground stations
    dashboard        $DASH
    Mission Planner  $MP
    results          data/flights/<today>_sim_NN_$NAME/   (also data/flights/latest)
    stop everything  scripts/stop_sim.sh
TXT
[ "$AUTO" = "1" ] || echo "    In the dashboard: Setup → Preflight → tick 'safety pilot ready' → START MISSION."
