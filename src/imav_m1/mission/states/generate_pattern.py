"""GENERATE_PATTERN — PORTED FROM SaR states/generate_pattern.py, generalised.

Reads shared["area"], plans the survey from config (survey.plan_survey), builds the full AUTO
mission (speed → survey lines → transit → NAV_LAND at the landing point) and stages it in shared.
No hard-coded coordinates anywhere: everything comes from the area inputs and the config.
"""

from __future__ import annotations

from ..items import build_survey_mission
from ..survey import plan_survey
from .common import MissionState


class GeneratePatternState(MissionState):
    name = "GENERATE_PATTERN"

    def execute(self) -> str:
        area = self.shared.get("area")
        if area is None:
            self.shared["last_error"] = "no area loaded"
            self.log("ERROR: no area loaded")
            self.shared.pop("return_stack", None)
            return self.return_next("IDLE")
        try:
            plan = plan_survey(area.survey, self.cfg)
            m = self.cfg["mission"]
            landing = area.landing or self.shared.get("home")
            precision = int(self.cfg.get("landing", {}).get("precision", 0))
            items, first, last = build_survey_mission(
                plan.waypoints,
                float(m["cruise_speed_mps"]),
                landing,
                float(m["cruise_alt_m"]),
                precision,
            )
        except Exception as e:  # noqa: BLE001
            self.shared["last_error"] = f"planning failed: {e}"
            self.log(f"ERROR: planning failed: {e}")
            self.shared.pop("return_stack", None)
            return self.return_next("IDLE")

        self.shared["survey_plan"] = plan
        self.shared["mission_items"] = items
        self.shared["survey_seq_range"] = (first, last)
        self.shared["mission_uploaded"] = False
        geometry = {
            "polygon": [list(p) for p in area.survey],
            "fence": [list(p) for p in area.fence],
            "waypoints": [[w.lat, w.lon] for w in plan.waypoints],
            "landing": list(landing) if landing else None,
        }
        self.shared["plan_geometry"] = geometry
        summary = plan.summary()
        summary["mission_items"] = len(items)
        summary["landing"] = landing
        self.push("plan", summary)
        self.push("plan_geometry", geometry)
        self.log(f"Plan: {summary}")
        if landing is None:
            self.log(
                "WARNING: no landing point and no home yet — NAV_LAND will land at the last waypoint"  # noqa: E501
            )
        return self.return_next("IDLE")
