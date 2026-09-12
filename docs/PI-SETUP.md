# Setting up the Raspberry Pi, step by step

Written for someone who has not used SSH much. Every step says what you should see if it worked, and
what to do when it does not. Do Parts 1 to 4 at a desk, with the props off, long before flight day.

Nothing here arms the aircraft. Props off for everything up to Part 6.

---

## Part 0 — What you need in front of you

- The Pi 5, with Raspberry Pi OS on the card, and a power supply that can do 5 V at 5 A. An underpowered
  supply causes reboots halfway through a flight, and it looks exactly like a software crash.
- Your laptop and the Pi on the **same network**. Same Wi-Fi, or both on the field router.
- The Cube wired to the Pi's serial pins, and the Cube powered.
- Roughly 30 minutes for the first time.

---

## Part 1 — Getting onto the Pi over SSH

SSH gives you a terminal on the Pi from your own laptop. You type on your laptop, it runs on the Pi.

### Step 1.1 — Open a terminal on your laptop

macOS: Terminal. Windows: PowerShell.

### Step 1.2 — Connect

```bash
ssh pi@raspberrypi.local
```

Replace `pi` with the Pi's username and `raspberrypi` with its hostname if they were changed at setup.

**First time only**, you get this:

```
The authenticity of host 'raspberrypi.local' can't be established.
ED25519 key fingerprint is SHA256:xxxxxxxx.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Type the whole word `yes` and press Enter. Just `y` is not accepted.

Then it asks for the password. **Nothing appears as you type**, no dots, no stars. That is normal.
Type it and press Enter.

Success looks like your prompt changing to something like `pi@raspberrypi:~ $`.

### Step 1.3 — When it does not connect

| What you see | What it means | Do this |
|---|---|---|
| `ssh: Could not resolve hostname` | The `.local` name is not resolving, common on Windows | Use the IP instead, see below |
| `Connection refused` | The Pi is reachable but SSH is switched off | Enable SSH, see below |
| `Operation timed out` / `No route to host` | Wrong network, or the Pi is not booted | Check both are on the same Wi-Fi; give the Pi 60 s from power-on |
| `Permission denied` | Wrong username or password | Default user is often `pi`; check with whoever imaged the card |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | The Pi was re-imaged | `ssh-keygen -R raspberrypi.local` then reconnect |

**Finding the Pi's IP address.** Easiest is to plug a monitor and keyboard into the Pi once and run
`hostname -I`, which prints something like `192.168.1.42`. Then connect with
`ssh pi@192.168.1.42`. Your router's admin page also lists connected devices.

**Enabling SSH if it is off.** Put the card in your laptop and create an empty file named `ssh`, with
no extension, in the boot partition. On the next boot SSH is on.

### Step 1.4 — Stop typing the password every time (optional, worth it)

On your laptop:

```bash
ssh-keygen -t ed25519          # press Enter at every prompt
ssh-copy-id pi@raspberrypi.local
```

After that `ssh pi@raspberrypi.local` logs straight in.

---

## Part 2 — Getting the code onto the Pi

The repository is private, so `git clone` on the Pi will ask for a GitHub login that the Pi does not
have. Two ways round it. **Route A is easier and works in a field with no internet.**

### Route A — copy it from your laptop (recommended)

Run this **on your laptop**, not on the Pi:

```bash
rsync -av --exclude .venv --exclude data/flights --exclude sim/runtime \
  ~/Desktop/IMAV2026-Outdoor-Mission1/ pi@raspberrypi.local:~/imav-m1/
```

Repeat that one command whenever the code changes. It only sends what differs.

### Route B — clone from GitHub with a token

On github.com: Settings → Developer settings → Personal access tokens → Fine-grained tokens. Give it
read access to this one repository. Then on the Pi:

```bash
git clone https://github.com/RobinCarter04/imav2026-outdoor-mission1.git ~/imav-m1
```

Username is your GitHub username. **Password is the token**, not your GitHub password.

---

## Part 3 — One-time Pi setup

All of this runs **on the Pi**, over SSH.

### Step 3.1 — Packages

```bash
sudo apt update
sudo apt install -y tmux python3-venv git
```

`tmux` is not optional. It is what stops a dropped Wi-Fi connection from killing a flight.

### Step 3.2 — Turn on the serial port

```bash
sudo raspi-config
```

Interface Options → Serial Port → **"login shell over serial?" No** → **"serial port hardware
enabled?" Yes** → Finish → reboot when asked.

Getting these two answers the wrong way round is the most common mistake here. The login shell must
be **off**, the hardware must be **on**.

After the reboot, reconnect and check:

```bash
ls -l /dev/serial0
```

You should see it pointing at `ttyAMA0`. Nothing listed means the previous step did not take.

### Step 3.3 — Let your user read the serial port

```bash
sudo usermod -a -G dialout $USER
```

**Log out and back in** for this to apply. Skipping the logout is why "permission denied" appears on
the serial port later.

### Step 3.4 — Install the code

```bash
cd ~/imav-m1
make setup
make test
```

`make test` should end with `59 passed`. If it does, the Pi side of the software is working, with no
aircraft involved.

If you see `error: externally-managed-environment`, you ran pip outside the virtual environment.
`make setup` creates one and installs into it. Do not use `--break-system-packages`.

> If the camera detector is going to share this Pi, it needs `picamera2` from apt rather than pip, and
> a virtual environment created with `--system-site-packages` so it can see it. Keep that separate
> from this one.

---

## Part 4 — Check the link to the flight controller, props off

Power the Cube. Props still off.

```bash
mavproxy.py --master=/dev/serial0,921600
```

You want to see heartbeats and a `Received N parameters` line within about 30 seconds.

Press Ctrl-C to quit once you have seen it.

| Problem | Cause | Fix |
|---|---|---|
| `Permission denied: '/dev/serial0'` | Not in the `dialout` group yet | Step 3.3, then log out and back in |
| `No such file or directory` | Serial hardware not enabled | Step 3.2 |
| Connects but silent, no heartbeat | Baud rate mismatch, or TX/RX swapped | Check `SERIALx_BAUD` on the Cube for the port the cable is in. TX on one side goes to RX on the other |
| Garbled characters | Baud mismatch | Same as above |

The baud must match the Cube's parameter for that port. `921600` is what we expect, confirm it.

---

## Part 5 — First run on the bench, props off

```bash
cd ~/imav-m1
./scripts/launch_hardware.sh --bench --gcs <your-laptop-ip>
```

`--bench` skips the flight preflight gate and says clearly that this session is **not cleared to
fly**. That is correct for ground testing.

Find your laptop's IP with `ipconfig getifaddr en0` on macOS or `ipconfig` on Windows.

You should land inside tmux with a window per process. On your laptop, open:

```
http://<pi-ip>:5000
```

The dashboard should show telemetry from the Cube. That means the whole chain works: Cube, serial,
Pi, mission code, your laptop.

If the page does not load, check you used the Pi's IP and that both machines are on the same network.

---

## Part 6 — Flight day sequence

Props on only at this point, and only with the safety pilot present.

```bash
ssh pi@raspberrypi.local
cd ~/imav-m1
./scripts/launch_hardware.sh --gcs <ground-station-ip>
```

This time there is no `--bench`, so the preflight gate runs. It refuses to launch if the tests fail,
the git tree is dirty, the polygons are not set or there is no parameter dump. That refusal is doing
its job. Fix the thing it names.

Then on the laptop, at `http://<pi-ip>:5000`: **Setup → Preflight → tick safety pilot ready → START.**

The aircraft does not move until someone presses START.

To stop everything:

```bash
./scripts/launch_hardware.sh --stop
```

---

## Part 7 — tmux, the five things you need

Everything runs inside tmux so a dropped SSH connection cannot kill a flight in progress.

| | |
|---|---|
| Leave it running and get your prompt back | **Ctrl-B** then **D** |
| Get back in after reconnecting | `tmux attach -t imav` |
| Switch between windows | **Ctrl-B** then **0**, **1**, **2** |
| Scroll back through output | **Ctrl-B** then **[**, arrow keys, **q** to leave |
| See if anything is running | `tmux ls` |

Ctrl-B is a prefix. Press and release it, then press the next key.

**If your Wi-Fi drops mid-flight, nothing bad happens to the aircraft.** Reconnect and
`tmux attach -t imav` to get your windows back.

---

## Part 8 — Things that go wrong, and what they mean

| Symptom | Likely cause |
|---|---|
| SSH worked yesterday, refuses today | Pi got a different IP from the router. Use the hostname, or check the router |
| Everything dies when you close the laptop lid | You ran it outside tmux. Use the launch script |
| Pi reboots during a run | Power supply cannot hold 5 A. Check the supply and the cable |
| `make test` fails on the Pi but passes on the laptop | Setup did not finish. Re-run `make setup` and read the errors |
| Dashboard loads but shows no telemetry | The MAVProxy bridge is not seeing the Cube. Go back to Part 4 |
| Preflight refuses to go green | Read the rows on the dashboard. GPS and EKF need ~30 seconds outdoors and never lock indoors |
| "Read-only file system" when writing logs | Some lab Pi images protect the root filesystem. `mount \| grep " / "`; if it says `overlay`, turn off the overlay in `raspi-config` → Performance Options |
| Clock is wrong, log timestamps look odd | No internet, so no time sync. Harmless for flying, annoying when comparing logs |

---

## The short version, once it is set up

```bash
ssh pi@raspberrypi.local
cd ~/imav-m1 && ./scripts/launch_hardware.sh --gcs <laptop-ip>
# laptop browser: http://<pi-ip>:5000
```
