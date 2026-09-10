"""ABORT — stop commanding, get the aircraft down safely, still produce the deliverables.

command_rtl=True  → we still own control (operator abort, battery, timeout): request RTL, monitor.
command_rtl=False → the pilot or a failsafe already has it: send nothing, just monitor to disarm.
Never disables failsafes, never re-arms. Then → REPORT so whatever was gathered is submitted.
"""

from __future__ import annotations

from .common import MissionState


class AbortState(MissionState):
    name = "ABORT"

    def enter(self) -> None:
        self.detector_mode("PASSIVE")
        self.log(f"ABORT — reason: {self.shared.get('abort_reason')}")
        self.push("abort", {"reason": self.shared.get("abort_reason"), "status": "ABORTING"})

    def execute(self) -> str:
        self.vehicle.drain()
        if self.vehicle.armed() is not True:
            self.log("not armed — nothing to bring down")
            self.push("abort", {"reason": self.shared.get("abort_reason"), "status": "ON GROUND"})
            return "REPORT"
        if self.shared.get("abort_command_rtl"):
            if self.vehicle.mode() in ("AUTO", "GUIDED"):
                ok = self.vehicle.set_mode("RTL")
                self.log("RTL requested" + ("" if ok else " — NOT confirmed; pilot must recover"))
            else:
                self.log(
                    f"mode is {self.vehicle.mode()} — pilot/failsafe has control, not commanding"
                )
        timeout = float(self.cfg.get("landing", {}).get("timeout_s", 600)) * 2
        start = self.now()
        while self.now() - start < timeout:
            self.vehicle.drain()
            self.record_telemetry()
            t = self.vehicle.telemetry()
            self.push(
                "abort",
                {
                    "reason": self.shared.get("abort_reason"),
                    "status": "RETURNING",
                    "mode": self.vehicle.mode(),
                    "alt": t.alt_rel_m,
                },
            )
            self.push_telemetry()
            if self.vehicle.armed() is False:
                self.shared["landed_time"] = self.now()
                self.log("disarmed — abort complete")
                self.push("abort", {"reason": self.shared.get("abort_reason"), "status": "LANDED"})
                return "REPORT"
            self.consume_command()  # swallow; nothing to do until on the ground
            self.sleep(self.tick())
        self.log("WARNING: abort timeout — still armed; handing to REPORT anyway")
        return "REPORT"
