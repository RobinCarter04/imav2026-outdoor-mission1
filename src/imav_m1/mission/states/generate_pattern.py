"""GENERATE_PATTERN — PORTED FROM SaR states/generate_pattern.py, generalised.

Reads shared["area"], plans the survey from config (survey.plan_survey), builds the full AUTO
mission (speed → survey lines → transit → NAV_LAND at the landing point) and stages it in shared.
No hard-coded coordinates anywhere: everything comes from the area inputs and the config.
"""

from __future__ import annotations

from ...config import effective_max_alt_m
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
            m = self.cfg["mission"]
            ceiling = effective_max_alt_m(self.cfg)
            if float(m["cruise_alt_m"]) > ceiling:
                raise ValueError(
                    f"cruise_alt_m {m['cruise_alt_m']} m is above the {ceiling:.0f} m ceiling for "
                    f"site '{area.site or self.cfg['site'].get('name')}'"
                )
            plan = plan_survey(area.survey_fly or area.survey, self.cfg)
            landing = area.landing or self.shared.get("home")
            precision = int(self.cfg.get("landing", {}).get("precision", 0))
            items, first, last = build_survey_mission(
                plan.waypoints,
                float(m["cruise_speed_mps"]),
                landing,
                float(m["cruise_alt_m"]),
                precision,
                transit_to_survey=area.transit_to_survey,
                transit_to_home=area.transit_to_home,
                transit_speed_mps=m.get("transit_speed_mps"),
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
            "exclusions": [[list(p) for p in e["points"]] for e in area.exclusions],
            "transit": [list(p) for p in (area.transit_to_survey + area.transit_to_home)],
            "fly_polygon": [list(p) for p in (area.survey_fly or area.survey)],
            "fence": [list(p) for p in area.fence],
            "waypoints": [[w.lat, w.lon] for w in plan.waypoints],
            "landing": list(landing) if landing else None,
        }
        self.shared["plan_geometry"] = geometry
        summary = plan.summary()
        summary["mission_items"] = len(items)
        summary["landing"] = landing
        summary["site"] = area.site
        summary["ceiling_m"] = ceiling
        summary["transit_waypoints"] = len(area.transit_to_survey) + len(area.transit_to_home)
        summary["exclusions"] = len(area.exclusions)
        self.push("plan", summary)
        self.push("plan_geometry", geometry)
        self.log(f"Plan: {summary}")
        if landing is None:
            self.log(
                "WARNING: no landing point and no home yet — NAV_LAND will land at the last waypoint"  # noqa: E501
            )
        return self.return_next("IDLE")
