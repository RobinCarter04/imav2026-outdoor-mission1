# Human reference

Short notes that save time. Skim it once, come back when something is odd.

## Running it

Three windows open on their own. SITL, optionally a Mission Planner bridge, then the mission.

```bash
make launch GCS=<vm-hostname>       # normal
make launch ARGS=--clean            # when it complains about leftovers
make launch SITE=fenswood
make stop
```

`make stop` before anything else if a run misbehaves. It kills SITL, the bridge, the mission and any
leftover detector.

Closing a Terminal window does not kill MAVProxy. It gets orphaned and keeps running, which is why
leftovers keep showing up.

**A ground station that is connected but not reading will freeze SITL.** The classic version is an
old MAVProxy nobody closed. Symptom: the aircraft stops moving and CPU sits near zero. `make stop`.

## Simulator gotchas

The simulated throttle stick sits at minimum. Selecting LOITER commands a full descent and the
aircraft lands and disarms in about 25 seconds. Two ways round it:

- take over with **GUIDED**, which ignores the sticks, or
- run `scripts/sitl_hold_sticks.sh` in a spare window first, then LOITER behaves.

Never use `sim_vehicle.py` on macOS. It launches the vehicle in its own Terminal window and the
scripts never see it. `scripts/start_sitl.sh` runs the binary directly.

Ports: **5760** ground station, **5762** mission code, **5763** a second ground station slot. Add 10
per instance, so `--instance 1` gives 5770, 5772, 5773.

`SPEEDUP=5 make launch` runs five times faster than real time. An eight minute survey takes ninety
seconds. Timings in the logs are simulated seconds.

The stock SITL battery runs flat mid-survey. `sim/sitl_params.parm` fits a 30 Ah pack so a full lap
finishes.

## The safety model

ArduPilot flies the aircraft. The mission uploads one AUTO mission and then watches. That matters:
if the mission code dies mid-flight, the aircraft keeps flying the uploaded mission and comes home.

The moment the flight mode leaves AUTO, the mission stops sending anything at all.

Getting it back needs **two** gates:

1. the pilot puts the aircraft in GUIDED or AUTO, and
2. the operator presses RESUME on the dashboard.

The RESUME button stays greyed out until gate 1 is satisfied. Pressing it early is refused and not
remembered, so press it again after the hand-back.

RTL or LAND from the pilot or from a failsafe is treated as an abort. No commands get sent. The
results still get written.

Arming needs an explicit START. Nothing arms on boot, on a timer, or on reconnect.

## Deliverables

Results are written on landing **and** after an abort, so a bad run still produces something.

You get a vehicle table in the rulebook's format, a map, a summary and a zip, under
`data/flights/<date>_<sim|hw>_NN_<name>/results/`. The dashboard shows a five minute countdown from
touchdown, which is the rulebook's submission window.

`data/flights/latest` always points at the current run.

## Config

Three layers, merged in order: `config/base.yaml`, then `config/sites/<site>.yaml`, then
`config/sim.yaml` or `config/hardware.yaml`.

Site files say **where**. Profile files say **how we connect**. Mission code never asks which profile
it is running under.

A site can lower the altitude ceiling and never raise it. Fenswood caps at 50 m and uses RTL on a
fence breach. Haguenau caps at 75 m under an 80 m rule.

Check what a command will actually use:

```bash
make check-config PROFILE=sim
.venv/bin/imav-m1 plan --profile sim --site fenswood      # plans, draws an SVG, flies nothing
```

Competition day: the organisers hand out the real corners. Draw them in Mission Planner, export KML,
then `--kml yourfile.kml`. That overrides the built-in area.

## On the aircraft

First time on a Pi, follow [PI-SETUP.md](PI-SETUP.md). After that:

```bash
ssh pi@<pi-hostname>
cd ~/imav-m1 && ./scripts/launch_hardware.sh --gcs <ground-station-ip>
```

Everything runs inside tmux, so a dropped SSH link does not kill a flight. Reconnect and
`tmux attach -t imav`. Ctrl-B then D detaches on purpose.

`--bench` skips the preflight gate for ground testing and says loudly that the session is not cleared
to fly. Props off.

The preflight gate blocks the launch if the tests fail, the git tree is dirty, the polygons are
missing or there is no parameter dump. That is deliberate.

## Debugging

| Symptom | Look at |
|---|---|
| Aircraft frozen, CPU near zero | A stale ground station on 5760. `make stop`. |
| "already running" on launch | Leftover processes. `make launch ARGS=--clean`. |
| Mission cannot connect | SITL not up yet, or a port clash. Try `--instance 1`. |
| Preflight never goes green | Read the failing rows on the dashboard. GPS and EKF need ~30 s. |
| Survey never starts | Mode is not AUTO, or the upload failed. Check the mission window. |
| Aircraft descends after LOITER | The simulated throttle stick. See the simulator section. |

Per-run logs live in the run folder: `telemetry.jsonl` for the flight, `detections/` for the
detector, `run.yaml` for the exact commit and config used.

## Before you fly for real

Work through `SIM_TO_REAL.md`. Short version: unit tests green, a nominal SITL run, the fault
scenarios, then props-off bench, then a hover, then a short survey with a safety pilot on the sticks.
