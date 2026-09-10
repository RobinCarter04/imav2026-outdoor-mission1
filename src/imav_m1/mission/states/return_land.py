"""RETURN_LAND — transit + NAV_LAND tail of the AUTO mission (precision-landing placeholder).

Monitors until the autopilot disarms on the ground. If the mission ends without landing (or takes
too long) it falls back to LAND mode. Same pilot/failsafe discipline as SURVEY. When precision
landing (R-12, ArUco) is added, this is where LANDING_TARGET streaming or PLND checks belong.
"""

from __future__ import annotations

from .common import MissionState


class ReturnLandState(MissionState):
    name = "RETURN_LAND"

    def enter(self) -> None:
        self.log("RETURN_LAND — transit to landing point and land (AUTO)")
        self.detector_mode("PASSIVE")

    def execute(self) -> str:
        ops = self.cfg.get("operator", {})
        timeout = float(self.cfg.get("landing", {}).get("timeout_s", 600))
        start = self.now()
        fallback_sent = False
        while True:
            self.vehicle.drain()
            mode = self.vehicle.mode()
            armed = self.vehicle.armed()
            t = self.vehicle.telemetry()
            cur, reached = self.vehicle.mission_progress()
            self.record_telemetry()
            self.push(
                "landing",
                {
                    "status": "LANDING" if (t.alt_rel_m or 0) < 3 else "RETURNING",
                    "alt": t.alt_rel_m,
                    "mode": mode,
                    "current_seq": cur,
                    "elapsed": self.elapsed_str("mission_start_time"),
                },
            )
            self.push_telemetry()
            if armed is False and self.shared.get("takeoff_time"):
                self.shared["landed_time"] = self.now()
                self.log("Disarmed on the ground — LANDED")
                self.push(
                    "landing",
                    {"status": "LANDED", "elapsed": self.elapsed_str("mission_start_time")},
                )
                return "REPORT"
            if mode not in ("AUTO", "LAND", "UNKNOWN"):
                if mode in ("RTL", "SMART_RTL"):
                    return self.go_abort(f"switched to {mode} during return", command_rtl=False)
                nxt = self.pilot_override_pause(mode, float(ops.get("override_timeout_s", 300)))
                if nxt:
                    return nxt
                continue
            if self.is_abort_command(self.consume_command()):
                return self.go_abort("operator abort during return", command_rtl=True)
            if not fallback_sent and self.now() - start > timeout:
                self.log("WARNING: landing timeout — requesting LAND mode as fallback")
                self.vehicle.set_mode("LAND")
                fallback_sent = True
            elif fallback_sent and self.now() - start > 2 * timeout:
                return self.go_abort("still airborne after LAND fallback", command_rtl=False)
            self.sleep(self.tick())
