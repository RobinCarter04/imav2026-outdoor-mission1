# Launching a session — one command

Two launchers, same shape: check what must be true, bring each stage up only once the previous one
is actually ready, and tell you where everything is.

| | Simulation, on the Mac | Hardware, on the aircraft's Pi |
|---|---|---|
| Command | `scripts/launch_sim.sh` | `./scripts/launch_hardware.sh` |
| Stages | SITL → (GCS bridge) → mission | MAVLink bridge → mission → detector |
| Runs in | three Terminal windows | one tmux session (survives a dropped SSH link) |
| Stop | `scripts/stop_sim.sh` | `./scripts/launch_hardware.sh --stop` |

Neither launcher can make the aircraft move. Arming needs a human pressing START in the dashboard
after the checks are green (`docs/SAFETY.md`).

---

## 1. Simulation

```bash
scripts/launch_sim.sh                                   # SITL + mission dashboard
scripts/launch_sim.sh --gcs ROBINCARTERC2F9.local       # + Mission Planner bridge in the VM
scripts/launch_sim.sh --kml sim/areas/haguenau_fig19.kml --speedup 5
scripts/launch_sim.sh --auto                            # scripted run, no clicking, writes results and exits
```

It opens one Terminal window per stage, waits for SITL's port before starting the next, gives GPS and
EKF time to settle, and opens the dashboard in your browser.

| Option | |
|---|---|
| `--gcs HOST` | also bridge to Mission Planner (UDP 14550). Without it, point Mission Planner at TCP `<this Mac>:5763` |
| `--kml FILE` | mission areas from a KML instead of `config/sim.yaml` |
| `--speedup N` | SITL faster than real time (5 turns an 8-minute survey into ~2) |
| `--auto` | scripted operator: setup → preflight → START, headless |
| `--instance N` | a second simulation alongside the first (ports 5770/5772, dashboard 5001) |
| `--clean` | stop leftover SITL / MAVProxy / mission processes first |
| `--wipe` | reset the simulated autopilot's stored parameters |
| `--dry-run` | print what it would launch, touch nothing |

**Leftovers matter.** An idle MAVProxy still attached to SITL's ground-station port freezes the
simulator: position stops advancing at almost no CPU. The launcher refuses to start when it finds
one; `--clean` clears them.

In the dashboard: **Setup → Preflight → tick "safety pilot ready" → START MISSION.**

Taking over from Mission Planner: switch to **GUIDED** (or LOITER) and the mission pauses instantly
and stops commanding. It stays paused until the pilot has the aircraft in GUIDED or AUTO **and** the
operator presses **RESUME** in the dashboard; the button is greyed out until the hand-back happens.
RTL or LAND aborts the mission without any command from us, and the results are still written.

In SITL the simulated throttle stick sits at minimum, so LOITER descends. Use GUIDED to take over,
or run `scripts/sitl_hold_sticks.sh` first — see `sim/README.md` §5b.

---

## 2. Hardware — the answer to "one SSH, one script"

> First time on a given Pi? Work through [PI-SETUP.md](PI-SETUP.md) first — SSH, serial port,
> packages and a props-off bench check. This section assumes that is done.


Yes, exactly that. From the ground-station laptop:

```bash
ssh pi@raspberrypi.local                     # your Pi's user and hostname
cd ~/imav-m1
git pull                                     # or rsync the repo across
./scripts/launch_hardware.sh --site imav --gcs 192.168.1.50
```

Then open `http://<pi-ip>:5000/` in the laptop's browser and fly the mission from there.

What that one command does:

1. Checks the virtualenv, the package, and that the autopilot serial port exists.
2. Runs the **flight preflight gate** (`scripts/preflight.sh`): clean git tree, tests passing,
   hardware profile loads, survey and fence polygons set, parameter dump present. It refuses to
   continue if any of that fails.
3. Starts MAVProxy on `/dev/ttyAMA0` at 921600, out to Mission Planner and to the mission's own
   port 14551 — the same bridge layout the SaR project flew.
4. Starts the mission and its detector.
5. Attaches you to tmux so you can watch all three.

**The SSH link dropping does not kill the flight.** Everything runs inside tmux, so a lost Wi-Fi
connection leaves the mission running; reconnect and run `tmux attach -t imav` to get the windows
back. Ctrl-B then D detaches on purpose. Without tmux installed the launcher falls back to detached
background processes with logs under `sim/runtime/`, which also survive, but tmux is worth the
`sudo apt install tmux`.

| Option | |
|---|---|
| `--gcs IP` | ground station for Mission Planner telemetry |
| `--site NAME` | which pre-programmed areas to fly: `imav` or `fenswood` |
| `--bench` | bring-up mode: skips the preflight gate, prints that the session is **not cleared to fly**. Props off |
| `--kml FILE` | competition-day areas |
| `--detector-cmd '…'` | run the teammate's detector instead of the placeholder |
| `--serial DEV` | autopilot serial port if it is not `/dev/ttyAMA0` |
| `--detach` | leave it running without attaching |
| `--stop` | stop the session |
| `--dry-run` | print the three commands, run nothing |

### First time on a new Pi

```bash
sudo apt install -y tmux python3-venv
git clone <repo> ~/imav-m1 && cd ~/imav-m1
make setup
./scripts/launch_hardware.sh --bench          # props OFF: link, dashboard and detector only
```

Work through `docs/SIM_TO_REAL.md` stage 3 on the bench before dropping `--bench`.
