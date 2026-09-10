"""DONE — terminal state: keep the dashboard live with the submission countdown; `reset` → IDLE."""

from __future__ import annotations

from .common import MissionState


class DoneState(MissionState):
    name = "DONE"

    def execute(self) -> str:
        res = self.shared.get("results", {})
        while True:
            self.vehicle.drain()
            self.push_telemetry()
            remaining = res.get("deadline", self.now()) - self.now()
            self.push(
                "results",
                {
                    **res,
                    "seconds_to_deadline": int(remaining),
                    "detections": len(self.detections()),
                },
            )
            if self.shared.get("stop_on_done"):
                self.shared["_stop"] = True
                return "DONE"
            cmd = self.consume_command()
            if cmd and cmd.get("type") == "reset":
                self.clear_mission_keys()
                self.log("reset — back to IDLE")
                return "IDLE"
            self.sleep(self.tick())
