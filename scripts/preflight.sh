#!/usr/bin/env bash
# Hardware preflight — run on the Pi before every real flight. Exits non-zero on any failure.
# SITE=imav|fenswood checks that site's areas (launch_hardware.sh passes it through).
# Automates what can be automated; the printed checklist covers the rest (docs/templates/flight_test_card.md).
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
fail=0; ok(){ echo "  [OK]   $*"; }; bad(){ echo "  [FAIL] $*"; fail=1; }; warn(){ echo "  [WARN] $*"; }

echo "== Preflight $(date -u +%Y-%m-%dT%H:%M:%SZ) =="
if git diff --quiet && git diff --cached --quiet; then ok "working tree clean"; else bad "uncommitted changes — commit or stash, then log the commit hash"; fi
echo "  commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'NO GIT')"
if git describe --tags --exact-match HEAD >/dev/null 2>&1; then ok "on tag $(git describe --tags --exact-match HEAD)"; else warn "HEAD is not a tagged release (expect comp-freeze at competition)"; fi

if .venv/bin/python -m pytest -q >/dev/null 2>&1; then ok "unit tests pass"; else bad "unit tests fail"; fi
if .venv/bin/python -m imav_m1.cli check-config --profile hardware >/dev/null 2>&1; then ok "hardware profile loads"; else bad "hardware profile does not load"; fi

# Resolve the areas the way the mission actually will (mission/area.py), so this gate sees the
# fence the site layer supplies through site.flight_area and not only an explicit
# safety.geofence.polygon override, and validate them rather than counting vertices.
areas=$(.venv/bin/python - "${SITE:-}" <<'PYEOF' 2>&1
import sys
from imav_m1.config import load_config
from imav_m1.mission.area import load_area_inputs, validate_area_inputs

site = sys.argv[1] or None
try:
    a = load_area_inputs(load_config("hardware", site))
    validate_area_inputs(a.survey, a.fence, a.landing, a.exclusions, a.transit_to_survey)
except Exception as e:
    print(f"BAD {type(e).__name__}: {e}")
else:
    where = a.site or a.source or "config"
    print(f"OK survey {len(a.survey)} pts, fence {len(a.fence)} pts (from {where})")
PYEOF
)
case "$areas" in
  OK*) ok "mission areas valid - ${areas#OK }" ;;
  *)   bad "mission areas invalid - ${areas#BAD }" ;;
esac

ls hardware/params/*.param >/dev/null 2>&1 && ok "param dump present: $(ls -t hardware/params/*.param | head -1)" || bad "no param dump in hardware/params/ (dump from GCS, record hash in docs/HARDWARE.md)"
[ -f hardware/calibration/imx296_intrinsics.yaml ] && ok "camera intrinsics present" || warn "camera intrinsics missing (georef accuracy will suffer)"
[ -e /dev/ttyAMA0 ] && ok "/dev/ttyAMA0 present" || warn "/dev/ttyAMA0 not present (not on the Pi?)"

cat <<'TXT'

Manual checks (tick on the flight test card):
  [ ] Battery voltage ≥ full; battery ID logged      [ ] Props tight, correct rotation
  [ ] Fence enabled + polygon loaded in GCS           [ ] RC failsafe verified (TX off → RTL)
  [ ] Safety pilot briefed on take-over switch        [ ] GPS 3D fix, HDOP ok, compass healthy
  [ ] Camera lens clean, mount rigid                  [ ] Log folder created under data/flights/
TXT
[ $fail -eq 0 ] && echo "== PREFLIGHT AUTOMATED CHECKS PASSED ==" || { echo "== PREFLIGHT FAILED — do not fly =="; exit 1; }
