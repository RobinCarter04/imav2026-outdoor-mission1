#!/usr/bin/env bash
# One-time: get an ArduPilot SITL binary on this machine.
#
#   scripts/setup_sitl.sh            find an existing build, or clone and build one
#   scripts/setup_sitl.sh --check    only report what is here, build nothing
#
# The simulator is not part of this repo (it is a separate ~1 GB project), so each laptop needs its
# own copy once. Budget 20-40 minutes the first time, and do it BEFORE you need it.
# Sets nothing permanently: it prints the ARDUPILOT_DIR line to add to your shell profile if the
# build ends up somewhere non-default.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_ONLY=0; [ "${1:-}" = "--check" ] && CHECK_ONLY=1

say()  { printf '\033[1m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# Anywhere a build might already be, most specific first.
CANDIDATES=(
  "${ARDUPILOT_DIR:-}"
  "$HOME/ardupilot"
  "$HOME/Desktop/MSc Aerial Robotics/Group Project Assignment/SITL/ardupilot"
)
for dir in "${CANDIDATES[@]}"; do
  [ -n "$dir" ] || continue
  if [ -x "$dir/build/sitl/bin/arducopter" ]; then
    say "SITL is already built: $dir/build/sitl/bin/arducopter"
    [ "$dir" = "$HOME/ardupilot" ] || echo "    add this to ~/.zshrc so the scripts find it:
        export ARDUPILOT_DIR='$dir'"
    echo "    try it:  make launch"
    exit 0
  fi
done

say "no ArduPilot SITL build found"
if [ "$CHECK_ONLY" = "1" ]; then
  echo "    run scripts/setup_sitl.sh (no --check) to clone and build one"
  exit 1
fi

TARGET="${ARDUPILOT_DIR:-$HOME/ardupilot}"
echo
echo "    This will clone ArduPilot into $TARGET and build the simulator."
echo "    Roughly 1 GB of download and 20-40 minutes of compiling. Needs internet."
echo
printf "    Continue? [y/N] "
read -r reply
case "$reply" in [yY]*) ;; *) echo "    cancelled"; exit 1 ;; esac

command -v git >/dev/null || die "git is not installed"
if [ "$(uname)" = "Darwin" ]; then
  command -v brew >/dev/null || warn "Homebrew not found — the prereq installer may ask for it (https://brew.sh)"
fi

if [ ! -d "$TARGET/.git" ]; then
  say "cloning ArduPilot into $TARGET (this is the slow bit)"
  git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git "$TARGET"
else
  say "checkout already at $TARGET, updating submodules"
  git -C "$TARGET" submodule update --init --recursive
fi

cd "$TARGET"
if [ "$(uname)" = "Darwin" ] && [ -x Tools/environment_install/install-prereqs-mac.sh ]; then
  say "installing build prerequisites (may ask for your password)"
  Tools/environment_install/install-prereqs-mac.sh -y || warn "prereq script reported a problem — continuing, the build will say if something is missing"
elif [ -x Tools/environment_install/install-prereqs-ubuntu.sh ]; then
  say "installing build prerequisites (may ask for your password)"
  Tools/environment_install/install-prereqs-ubuntu.sh -y || warn "prereq script reported a problem — continuing"
fi

say "configuring and building ArduCopter for SITL"
./waf configure --board sitl
./waf copter

[ -x "$TARGET/build/sitl/bin/arducopter" ] || die "build finished but no binary at $TARGET/build/sitl/bin/arducopter — read the output above"
say "built: $TARGET/build/sitl/bin/arducopter"
[ "$TARGET" = "$HOME/ardupilot" ] || echo "    add to ~/.zshrc:  export ARDUPILOT_DIR='$TARGET'"
echo
echo "    now run:  cd '$HERE' && make launch"
