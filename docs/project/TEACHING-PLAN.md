# Teaching plan — getting the team flight-ready without you

Goal for the session: by the end, each teammate can run a full simulated mission alone, take control
and hand it back, and say what the aircraft will do if something goes wrong. That is the bar. Not
"understands the code".

Budget 90 minutes. The hands-on blocks are the ones that matter; cut the talking first.

## Before the meeting (10 minutes)

- Push the repo and send the link.
- Ask everyone to run `make setup` and `make test` **before** they arrive. Setup on a cold laptop is
  the single biggest time sink and it is boring to watch.
- Have one SITL session already running on your machine as a fallback demo.

## 1. What it does, in one lap (10 min, you drive)

Run `make launch GCS=<vm>` on the projector and fly a whole mission while you narrate.

Say only this much:
- One AUTO mission is uploaded: take off, survey lines, come home, land.
- ArduPilot flies it. Our code watches and records.
- On touchdown it writes the submission: vehicle table, map, zip.
- The only button a human presses is START.

Show the results folder at the end. That is the product.

## 2. Everyone runs it (20 min, hands on)

Let them work in pairs. Target: dashboard open, mission flown, results file opened.

```bash
make launch
# Setup → Preflight → tick safety pilot ready → START
make stop
```

Expect these three to come up, and let them hit them rather than pre-empting:
- leftover processes, fixed with `ARGS=--clean`
- preflight not green for the first ~30 seconds while GPS and EKF settle
- someone closing a window and wondering why the port is still busy

## 3. The mental model (15 min, whiteboard)

Three ideas, nothing more.

**ArduPilot flies, we watch.** If our code dies mid-flight the aircraft still finishes and comes
home. That is why the mission is one upload rather than a stream of commands.

**Three config layers.** `base.yaml` for defaults and safety caps, `sites/<site>.yaml` for where,
`sim.yaml` or `hardware.yaml` for how we connect. Show `--site fenswood` changing the whole flight.

**A site can only tighten limits.** Fenswood caps at 50 m and turns a fence breach into RTL. Show the
line in the file, then the log line where it takes effect.

Do not teach the internals of the survey planner or the state machine. Nobody needs it to fly.

## 4. Taking control (20 min, hands on — the important block)

This is the part that decides whether they can fly without you.

Run a mission, then have each person do all of it from Mission Planner:

1. Switch to GUIDED mid-survey. Watch the dashboard go PAUSED and the RESUME button grey out.
2. Press RESUME too early while still in LOITER. Watch it get refused.
3. Hand back to GUIDED, then press RESUME. Watch the survey continue.
4. Switch to RTL. Watch it abort without sending anything, and still write results.

Points to land while they do it:
- The mission stops sending anything the instant the mode leaves AUTO.
- Two gates to resume: pilot hands back, operator presses the button.
- In SITL, LOITER descends because the simulated throttle stick sits at minimum. Use GUIDED, or run
  `scripts/sitl_hold_sticks.sh`. On the real aircraft this does not happen.

## 5. When it goes wrong (15 min)

Break it on purpose and let them diagnose from the dashboard and the log.

- Leave a stale MAVProxy running, start a mission, watch SITL freeze at zero CPU.
- Kill the mission process mid-flight. The aircraft carries on and lands.
- Set the cruise altitude above the site ceiling and watch planning refuse.

Then walk the debugging table in `docs/HUMAN-REFERENCE.md` so they know where it lives.

## 6. Hardware day (10 min, talk only)

- One SSH session, one script, everything inside tmux so a dropped link cannot kill a flight.
- `--bench` for ground testing, props off, and it says it is not cleared to fly.
- The preflight gate refuses to launch on a dirty tree or failing tests. That is deliberate.
- Walk `SIM_TO_REAL.md` top to bottom. Nobody flies a stage they have not passed.

## 7. Roles and homework (10 min)

Agree who is safety pilot, who runs the dashboard, and who handles the submission. Write it down.

Homework, one each:
- Fly both sites solo and send the results zip.
- Read `docs/HUMAN-REFERENCE.md` end to end.
- Run one fault drill and describe what happened.

## Sign-off: six things, unaided

Each person demonstrates these without help. This is the actual test of "can fly without Robin".

1. Start a session and fly a mission to a written results file.
2. Change site and say what changed about the flight.
3. Take control mid-survey and hand it back correctly.
4. Force an abort and find the results it still wrote.
5. Recover from leftover processes and from a frozen simulator.
6. Say what the aircraft does if the Pi dies at the far end of the survey.

## If you only get 30 minutes

Sections 2 and 4. Running it, and taking control. Everything else can be read.
