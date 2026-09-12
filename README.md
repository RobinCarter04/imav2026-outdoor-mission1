# IMAV 2026 — Outdoor Mission 1

Autonomous mapping and vehicle identification for the IMAV 2026 outdoor competition, flown on an
ArduPilot multirotor with a Raspberry Pi companion computer.

One AUTO mission does the whole flight: take off, fly a survey pattern over the area, return, land.
A detector runs alongside and reports vehicles it finds. On touchdown the code writes the
competition submission: a table of vehicles with GPS coordinates, a map, and a zip of both.

The only manual step is pressing START. A safety pilot can take control at any moment.

## Get it running in five minutes

```bash
make setup                              # once: virtualenv + install
make test                               # must be green
make launch                             # SITL + mission dashboard, a window each
make launch SITE=fenswood               # the Fenswood Farm test area instead
make launch GCS=<windows-vm-hostname>   # and Mission Planner spectating
make stop                               # stop everything
```

The dashboard opens at http://localhost:5000. Work down it: **Setup → Preflight → tick "safety pilot
ready" → START MISSION.**

## Read these, in this order

| | |
|---|---|
| [docs/HUMAN-REFERENCE.md](docs/HUMAN-REFERENCE.md) | The things that save you an hour. Read this one first. |
| [docs/LAUNCH.md](docs/LAUNCH.md) | Every way to start a session, on the laptop and on the Pi |
| [docs/SAFETY.md](docs/SAFETY.md) | Non-negotiable rules. Read before touching hardware. |
| [docs/SIM_TO_REAL.md](docs/SIM_TO_REAL.md) | The gate code passes through before it flies |
| [docs/AI-GUIDE.md](docs/AI-GUIDE.md) | Using Claude Code on this repo without breaking it |
| [docs/HARDWARE.md](docs/HARDWARE.md) | What is on the aircraft |
| [docs/DETECTION_INTERFACE.md](docs/DETECTION_INTERFACE.md) | For whoever writes the detector |

Background, planning and history live in [docs/project/](docs/project/). None of it is needed to fly.

## Where the code is

```
config/          base.yaml + sites/<site>.yaml + sim.yaml | hardware.yaml
src/imav_m1/
  mission/       state machine, states/, survey planning, geometry, mission items
  vehicle/       MAVLink (the only place pymavlink is imported) + a fake for tests
  detection/     the file contract with the detector, plus a placeholder detector
  mapping/       the results writer: vehicle table, map, zip
  ops/           operator dashboard
scripts/         launch_sim.sh, launch_hardware.sh, start_sitl.sh, preflight.sh, stop_sim.sh
tests/           unit/ runs the whole mission on a fake vehicle, no simulator needed
sim/             SITL runbook, start locations, the digitised competition areas
```

## Two sites

`--site imav` is the competition field at Haguenau. `--site fenswood` is Fenswood Farm, carried over
from the search-and-rescue project, including its SSSI no-fly zone and the corridor that routes
around it. A site can tighten the safety limits and never loosen them.
