# Using an AI assistant on this repo

Written for Claude Code, but any assistant that can read files and run commands works the same way.

## Start here

Open a terminal in the repo root and run `claude`. The assistant reads `CLAUDE.md` on its own, which
tells it the architecture, the layout rules and the safety rules. You do not need to paste any of it.

Say what you want in plain language. Name the file if you know it.

## What it must never do

These are already in `CLAUDE.md`, repeated here so you can spot it going wrong:

- Change `config/hardware.yaml`, any `safety:` block, or anything in `hardware/params/` unless you
  asked for that exact change in that conversation.
- Write code that bypasses pre-arm checks, disables a failsafe or a fence, or arms automatically.
- Invent rulebook facts. It cites a section or writes TBD.
- Leave `make test` red.

If you see it do any of those, stop and say so. It should be flagging the concern, not working
around it.

## Prompts that work

```
run the mission in SITL at fenswood and tell me what happened
the survey never starts, here is the mission window output: <paste>
add a state that does X, with a unit test, following the existing states
why does the aircraft descend when I select LOITER?
explain what generate_pattern.py does, I have to teach it tomorrow
plan the survey for fenswood and tell me the flight time
```

Two habits worth keeping:

- Ask it to run `make test` before it says something is done.
- Ask what it verified. "Tests pass" and "I flew it in SITL and watched the result" are different
  claims, and it should tell you which one it is making.

## What to paste when something breaks

The assistant can read the repo, so it needs the transient bits:

- the run folder name, for example `data/flights/2026-09-12_sim_03_mission`
- the last twenty lines of the mission window
- what you were doing and what you expected

It can then read `telemetry.jsonl`, `run.yaml` and the results itself.

## Traps worth mentioning up front

Say these out loud if the assistant starts guessing:

- The simulated throttle stick sits at minimum, so LOITER descends in SITL. It is not a code bug.
- A connected but idle ground station freezes SITL.
- `sim_vehicle.py` opens its own Terminal window on macOS and must not be used.
- Background processes it starts may not survive its own shell, so a simulator it launched in one
  command can be gone by the next one.

## Making a change safely

The whole mission runs in unit tests against a fake vehicle, with no simulator, in under a second.
Ask for a test alongside any change to `mission/` or `vehicle/`, then:

```bash
make test && make lint
make launch SITE=fenswood        # watch it fly the change
```

Ask it to append to `docs/project/PROGRESS_LOG.md` at the end of a working session, with what
changed, how it was tested and what the result was. That file is how the next person catches up.

## What it is good and bad at here

Good: reading the whole pipeline and explaining it, writing tests, planning surveys, hunting through
telemetry logs, tracing a symptom to a file.

Bad: anything needing real hardware or real eyes. It cannot tell you whether the camera is mounted
square, whether the prop nuts are tight, or whether the field is clear. Those stay with you.
