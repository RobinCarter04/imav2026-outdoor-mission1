"""UPLOAD_FENCE — PORTED FROM SaR states/upload_fence.py.

Pushes the fence parameters from cfg.safety.geofence (read-only) and uploads the flight-area
inclusion polygon. Every upload REPLACES the whole fence list on the autopilot, so all polygons go
in one transaction. Rulebook §2: max 80 m AGL (we use cfg max_alt_m), breach → land.
"""

from __future__ import annotations

from ...vehicle.interface import FencePolygon
from .common import MissionState

FENCE_ACTIONS = {"report": 0, "rtl": 1, "land": 2, "smart_rtl": 3, "brake": 4}
FENCE_TYPE_ALT_MAX = 1
FENCE_TYPE_POLYGON = 4


class UploadFenceState(MissionState):
    name = "UPLOAD_FENCE"

    def execute(self) -> str:
        area = self.shared.get("area")
        if area is None or len(area.fence) < 3:
            self.log("ERROR: no fence polygon")
            self.shared["fence_uploaded"] = False
            self.shared.pop("return_stack", None)
            return self.return_next("IDLE")
        gf = self.cfg["safety"]["geofence"]
        if not gf.get("enabled", True):
            self.log("WARNING: safety.geofence.enabled is false — skipping fence upload")
            self.shared["fence_uploaded"] = False
            return self.return_next("IDLE")

        params = [
            ("FENCE_ENABLE", 1.0),
            ("FENCE_TYPE", float(FENCE_TYPE_ALT_MAX | FENCE_TYPE_POLYGON)),
            ("FENCE_ACTION", float(FENCE_ACTIONS.get(str(gf.get("action", "land")).lower(), 2))),
            ("FENCE_ALT_MAX", float(gf["max_alt_m"])),
            ("FENCE_MARGIN", float(gf.get("margin_m", 2.0))),
        ]
        for name, value in params:
            self.vehicle.set_param(name, value)
            self.log(f"  {name} = {value}")

        polygons = [FencePolygon("inclusion", tuple(area.fence), "Flight area")]
        ok = self.vehicle.upload_fence(polygons)
        count = self.vehicle.fence_count() if ok else 0
        ok = ok and count >= len(area.fence)
        self.shared["fence_uploaded"] = ok
        self.push(
            "fence",
            {
                "uploaded": ok,
                "vertices": count,
                "action": gf.get("action"),
                "alt_max": gf["max_alt_m"],
            },
        )
        self.log(f"Fence upload {'OK' if ok else 'FAILED'} ({count} vertices on autopilot)")
        if not ok:
            self.shared.pop("return_stack", None)
        return self.return_next("IDLE")
