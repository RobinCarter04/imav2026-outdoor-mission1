# Safety rules — non-negotiable

These apply to every human and every AI assistant working on this code.

## Code rules
1. **Never disable, weaken, or work around** ArduPilot pre-arm checks, geofence, RC failsafe, battery
   failsafe, or EKF failsafes in code or in params committed to this repo.
2. **Arming is an explicit operator action** (GUI button / trigger file / CLI confirm). Code must never
   arm on boot, on timer, or as a side-effect.
3. The mission code **sends** guided/mission commands; it never assumes it is the only thing in control.
   If the autopilot changes mode on its own (failsafe, pilot override), the code must notice and stop
   commanding.
4. Safety-critical values (`safety:` block in config, anything under `hardware/params/`) are changed
   only by a human, on purpose, with a PROGRESS_LOG entry saying why.
5. Any AI-generated change touching `vehicle/`, `mission/`, or `config/hardware.yaml` is reviewed by a
   human before it runs on hardware. No exceptions for "small" changes.

## Flight rules
- Safety pilot on the RC at all times, in a mode they can take over with one switch (verify the switch
  does what you think it does — on the bench, props off).
- Geofence enabled with RTL action for every flight, sim and real. Fence polygon logged with the flight.
- Props off for every bench test. Battery disconnected when working on wiring.
- Preflight checklist (`scripts/preflight.sh` + printed card) every flight, even the "quick" ones.
- No flight after a code or param change that has not been through `SIM_TO_REAL.md` for its stage.
- Competition rules on safety pilot, frequencies, and MTOW override anything here if stricter.
- Rulebook V4 §2 specifics: kill switch on the RC (mandatory); max 80 m AGL (our fence: 75 m); leaving the
  flight zone → land, further → motor cut (so `safety.geofence.action` is `land`); MTOW 5 kg; radio power
  limits in §2.1 (2.4 / 5.8 GHz ≤ 25 mW).

## Emergency procedures (fill in with the team, print, tape to the GCS case)
| Situation | Action |
|---|---|
| Aircraft not responding to mission code | Safety pilot switches to LOITER/RTL; do not restart code in flight |
| Fly-away / fence breach | Safety pilot RTL; if no response, LAND; announce loudly |
| Link loss | Wait for autopilot failsafe RTL; prepare for manual recovery |
| Person enters the area | Safety pilot LOITER; pause mission; resume only when clear |
| Battery low earlier than expected | RTL immediately; note capacity in log |
