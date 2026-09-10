"""UPLOAD_MISSION — PORTED FROM SaR states/upload_mission.py (mission items, not waypoints)."""

from __future__ import annotations

from .common import MissionState


class UploadMissionState(MissionState):
    name = "UPLOAD_MISSION"

    def execute(self) -> str:
        items = self.shared.get("mission_items")
        if not items:
            self.log("ERROR: no mission items staged")
            self.shared["mission_uploaded"] = False
            self.shared.pop("return_stack", None)
            return self.return_next("IDLE")
        ok = self.vehicle.upload_mission(items)
        count = self.vehicle.mission_count() if ok else 0
        ok = ok and count == len(items)
        self.shared["mission_uploaded"] = ok
        self.push("mission", {"uploaded": ok, "items": count, "expected": len(items)})
        self.log(
            f"Mission upload {'OK' if ok else 'FAILED'} ({count}/{len(items)} items on autopilot)"
        )
        if not ok:
            self.shared.pop("return_stack", None)
        return self.return_next("IDLE")
