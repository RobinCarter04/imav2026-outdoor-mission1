"""TAKEOFF — PORTED FROM SaR states/guided_takeoff.py, then hands over to AUTO.

GUIDED → arm → NAV_TAKEOFF to cruise altitude → altitude reached → AUTO → SURVEY.
Failures on the ground go back to IDLE; failures once airborne go to ABORT (which lands via RTL).
"""

from __future__ import annotations

from .common import MissionState


class TakeoffState(MissionState):
    name = "TAKEOFF"

    def execute(self) -> str:
        pf = self.cfg.get("preflight", {})
        alt = float(self.cfg["mission"]["cruise_alt_m"])
        tol = float(pf.get("altitude_tolerance_m", 3.0))
        self.vehicle.drain()
        if self.vehicle.armed():
            self.log("WARNING: already armed — refusing to run the takeoff sequence")
            return "IDLE"
        if not self.vehicle.set_mode("GUIDED"):
            return self._ground_fail("could not enter GUIDED")
        if not self.vehicle.arm(float(pf.get("arm_timeout_s", 15))):
            return self._ground_fail("arming failed (pre-arm checks?)")
        self.log(f"Armed — takeoff to {alt} m")
        self.vehicle.takeoff(alt)
        self.shared["takeoff_time"] = self.now()
        self.detector_mode("PASSIVE")

        deadline = self.now() + float(pf.get("takeoff_timeout_s", 90))
        last_log = 0.0
        while self.now() < deadline:
            self.vehicle.drain()
            t = self.vehicle.telemetry()
            mode = self.vehicle.mode()
            self.record_telemetry()
            self.push("takeoff", {"target_alt": alt, "alt": t.alt_rel_m, "mode": mode})
            self.push_telemetry()
            if mode not in ("GUIDED", "UNKNOWN"):
                return self.go_abort(
                    f"mode changed to {mode} during takeoff (pilot/failsafe)", command_rtl=False
                )
            if self.is_abort_command(self.consume_command()):
                return self.go_abort("operator abort during takeoff", command_rtl=True)
            if t.alt_rel_m is not None and abs(t.alt_rel_m - alt) <= tol:
                self.log(f"Target altitude reached: {t.alt_rel_m:.1f} m — switching to AUTO")
                if not self.vehicle.set_mode("AUTO"):
                    return self.go_abort("AUTO not accepted after takeoff", command_rtl=True)
                self.shared["survey_start_time"] = self.now()
                return "SURVEY"
            if self.now() - last_log > 5:
                self.log(f"climbing {t.alt_rel_m} -> {alt} m")
                last_log = self.now()
            self.sleep(self.tick())
        return self.go_abort("takeoff timeout — altitude not reached", command_rtl=True)

    def _ground_fail(self, why: str) -> str:
        self.shared["last_error"] = f"takeoff: {why}"
        self.log(f"ERROR: {why}")
        return "IDLE"
