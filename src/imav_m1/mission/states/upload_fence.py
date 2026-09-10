"""UPLOAD_FENCE — PORTED FROM SaR states/upload_fence.py.

Pushes the fence parameters from cfg.safety.geofence (read-only) and uploads the flight-area
inclusion polygon together with every exclusion zone. An upload REPLACES the autopilot's whole
fence list, so they must all go in one transaction or the earlier ones vanish.

Ceiling and breach action are the TIGHTER of the global `safety.geofence` values and the site's
own (`site.max_alt_m`, `site.fence_action`) — see config.effective_max_alt_m.
"""

from __future__ import annotations

from ...config import effective_fence_action, effective_max_alt_m
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

        ceiling = effective_max_alt_m(self.cfg)
        action = effective_fence_action(self.cfg)
        if ceiling < float(gf["max_alt_m"]):
            self.log(
                f"site ceiling {ceiling:.0f} m is tighter than "
                f"the {gf['max_alt_m']} m cap — using it"
            )
        params = [
            ("FENCE_ENABLE", 1.0),
            ("FENCE_TYPE", float(FENCE_TYPE_ALT_MAX | FENCE_TYPE_POLYGON)),
            ("FENCE_ACTION", float(FENCE_ACTIONS.get(action, 2))),
            ("FENCE_ALT_MAX", ceiling),
            ("FENCE_MARGIN", float(gf.get("margin_m", 2.0))),
        ]
        for name, value in params:
            self.vehicle.set_param(name, value)
            self.log(f"  {name} = {value}")

        # A fence upload REPLACES the autopilot's whole list, so the flight area and
        # every exclusion zone must go up together or the earlier ones vanish (SaR upload_fence.py).
        polygons = [FencePolygon("inclusion", tuple(area.fence), "Flight area")]
        polygons += [
            FencePolygon("exclusion", tuple(z["points"]), z["name"]) for z in area.exclusions
        ]
        expected = sum(len(p.points) for p in polygons)
        ok = self.vehicle.upload_fence(polygons)
        count = self.vehicle.fence_count() if ok else 0
        ok = ok and count >= expected
        self.shared["fence_uploaded"] = ok
        self.push(
            "fence",
            {
                "uploaded": ok,
                "vertices": count,
                "expected": expected,
                "action": action,
                "alt_max": ceiling,
                "exclusions": [z["name"] for z in area.exclusions],
            },
        )
        self.log(
            f"Fence upload {'OK' if ok else 'FAILED'} — {count}/{expected} vertices, "
            f"action={action}, ceiling={ceiling:.0f} m, "
            f"exclusions: {[z['name'] for z in area.exclusions] or 'none'}"
        )
        if not ok:
            self.shared.pop("return_stack", None)
        return self.return_next("IDLE")
