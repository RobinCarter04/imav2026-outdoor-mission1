"""Mission area inputs: survey polygon(s), flight-area fence, landing point.

Sources, in priority order:
  1. a KML file (`imav-m1 run --kml file.kml`) — draw the areas in Mission Planner / Google Earth on
     the day (rulebook §5.2: corners are given on competition day), placemark names below;
  2. the merged config: `mission.survey.area_polygon`, `safety.geofence.polygon`, `landing.point`.
Fence: `safety.geofence.polygon` if set (explicit override), else the selected site's
`site.flight_area`. Exclusion zones, and the transit corridors that route around them, come from the
site too (`site.exclusions`, `site.transit_to_survey`, `site.transit_to_home`).

KML parsing PORTED FROM: SaR sarFlightDay4/kml_parser.py (stdlib xml.etree only).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import geo
from .geo import LatLon

KML_NS = "{http://www.opengis.net/kml/2.2}"

# Placemark names we look for (case-insensitive, first match wins).
PLACEMARK_NAMES = {
    "survey": ["Mapping Area 1", "Survey Area", "Search Area", "Area 1"],
    "survey2": ["Mapping Area 2", "Area 2"],
    "fence": ["Flight Area", "Fence", "Geofence"],
    "landing": ["Landing", "Landing Zone", "Take-Off Location", "TOL", "Home"],
}
# Any placemark whose name matches one of these becomes an EXCLUSION fence (a no-fly zone).
EXCLUSION_NAMES = ("sssi", "exclusion", "no fly", "no-fly", "keep out", "keepout")


@dataclass
class AreaInputs:
    survey: list[LatLon]
    fence: list[LatLon]
    landing: LatLon | None
    survey2: list[LatLon] | None = None
    source: str = "config"
    notes: list[str] = field(default_factory=list)
    survey_fly: list[LatLon] = field(
        default_factory=list
    )  # survey inset by edge_margin_m — what we fly
    margin_m: float = 0.0
    exclusions: list[dict] = field(default_factory=list)  # [{"name": str, "points": [LatLon]}]
    transit_to_survey: list[LatLon] = field(default_factory=list)  # corridor before the survey
    transit_to_home: list[LatLon] = field(default_factory=list)  # corridor after the survey
    site: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "survey_vertices": len(self.survey),
            "survey_area_ha": round(geo.polygon_area_m2(self.survey) / 10_000.0, 2),
            "site": self.site,
            "fence_vertices": len(self.fence),
            "exclusions": [f"{e['name']} ({len(e['points'])} pts)" for e in self.exclusions],
            "transit_waypoints": [len(self.transit_to_survey), len(self.transit_to_home)],
            "edge_margin_m": self.margin_m,
            "fly_area_ha": round(geo.polygon_area_m2(self.survey_fly or self.survey) / 10_000.0, 2),
            "landing": self.landing,
            "notes": list(self.notes),
        }


# ── KML ───────────────────────────────────────────────────────────────────────────────────────


def parse_kml(path: str | Path) -> dict[str, list[LatLon]]:
    """Return {placemark name: [(lat, lon), ...]} for every Polygon / Point placemark."""
    root = ET.parse(str(path)).getroot()
    out: dict[str, list[LatLon]] = {}
    for pm in root.iter(f"{KML_NS}Placemark"):
        name_el = pm.find(f"{KML_NS}name")
        if name_el is None or not name_el.text:
            continue
        name = name_el.text.strip()
        poly = pm.find(f".//{KML_NS}Polygon")
        if poly is not None:
            el = poly.find(f".//{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates")
            if el is not None and el.text:
                coords = _parse_coords(el.text)
                if len(coords) > 1 and coords[0] == coords[-1]:
                    coords = coords[:-1]
                out[name] = coords
                continue
        point = pm.find(f".//{KML_NS}Point")
        if point is not None:
            el = point.find(f"{KML_NS}coordinates")
            if el is not None and el.text:
                out[name] = _parse_coords(el.text)
    return out


def _parse_coords(text: str) -> list[LatLon]:
    coords = []
    for token in text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            coords.append((float(parts[1]), float(parts[0])))  # KML is lon,lat,alt
    return coords


def _find(placemarks: dict[str, list[LatLon]], key: str) -> list[LatLon] | None:
    lower = {k.lower(): v for k, v in placemarks.items()}
    for name in PLACEMARK_NAMES[key]:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


# ── loading + validation ──────────────────────────────────────────────────────────────────────


def _pairs(raw: Any) -> list[LatLon]:
    return [(float(p[0]), float(p[1])) for p in (raw or [])]


def load_area_inputs(cfg: dict[str, Any], kml_path: str | Path | None = None) -> AreaInputs:
    notes: list[str] = []
    site_cfg = cfg.get("site") or {}
    survey = _pairs(cfg["mission"]["survey"].get("area_polygon"))
    survey2 = _pairs(cfg["mission"]["survey"].get("area2_polygon")) or None
    fence = _pairs(cfg["safety"]["geofence"].get("polygon"))
    exclusions = [
        {"name": str(e.get("name") or f"exclusion {i + 1}"), "points": _pairs(e.get("points"))}
        for i, e in enumerate(site_cfg.get("exclusions") or [])
    ]
    transit_out = _pairs(site_cfg.get("transit_to_survey"))
    transit_home = _pairs(site_cfg.get("transit_to_home"))
    landing_raw = cfg.get("landing", {}).get("point")
    landing = (float(landing_raw[0]), float(landing_raw[1])) if landing_raw else None
    source = "config"

    if kml_path:
        pms = parse_kml(kml_path)
        source = f"kml:{Path(kml_path).name}"
        s = _find(pms, "survey")
        if s:
            survey = s
        else:
            notes.append(f"KML has no survey placemark ({PLACEMARK_NAMES['survey']}); using config")
        s2 = _find(pms, "survey2")
        if s2:
            survey2 = s2
        f = _find(pms, "fence")
        if f:
            fence = f
        ld = _find(pms, "landing")
        if ld:
            landing = ld[0]
        from_kml = [
            {"name": name, "points": pts}
            for name, pts in pms.items()
            if len(pts) >= 3 and any(k in name.lower() for k in EXCLUSION_NAMES)
        ]
        if from_kml:
            exclusions = from_kml

    if not fence:
        fence = _pairs(site_cfg.get("flight_area"))
        notes.append(f"fence from site '{site_cfg.get('name')}' (site.flight_area)")

    margin = float(cfg["mission"]["survey"].get("edge_margin_m", 0.0) or 0.0)
    if len(survey) >= 3 and margin > 0:
        try:
            survey_fly = geo.inset_polygon(survey, margin)
        except ValueError as e:
            raise ValueError(f"survey edge_margin_m={margin}: {e}") from e
    else:
        survey_fly = list(survey)
    validate_area_inputs(survey_fly, fence, landing, exclusions, transit_out + transit_home)
    if len(fence) >= 3:
        outside = [p for p in survey if not geo.point_in_polygon(p, fence)]
        if outside:
            notes.append(
                f"{len(outside)} survey vertex/vertices lie on or outside the fence — "
                f"flight path is inset by {margin} m"
            )
    return AreaInputs(
        survey,
        fence,
        landing,
        survey2,
        source,
        notes,
        survey_fly,
        margin,
        exclusions,
        transit_out,
        transit_home,
        str(site_cfg.get("name") or ""),
    )


def validate_area_inputs(
    survey: list[LatLon],
    fence: list[LatLon],
    landing: LatLon | None,
    exclusions: list[dict] | None = None,
    transit: list[LatLon] | None = None,
) -> None:
    if len(survey) < 3:
        raise ValueError(
            "survey polygon needs >= 3 vertices (set mission.survey.area_polygon or pass --kml)"
        )
    if len(fence) < 3:
        raise ValueError("fence polygon needs >= 3 vertices")
    for lat, lon in survey + fence:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"coordinate out of range: {lat}, {lon}")
    outside = [p for p in survey if not geo.point_in_polygon(p, fence)]
    if outside:
        raise ValueError(
            f"{len(outside)} survey vertex/vertices lie outside the fence: {outside[:2]}"
        )
    if landing is not None and not geo.point_in_polygon(landing, fence):
        raise ValueError(f"landing point {landing} lies outside the fence")
    for wp in transit or []:
        if not geo.point_in_polygon(wp, fence):
            raise ValueError(f"transit waypoint {wp} lies outside the fence")
    for zone in exclusions or []:
        pts = zone["points"]
        if len(pts) < 3:
            raise ValueError(f"exclusion '{zone['name']}' needs >= 3 vertices, got {len(pts)}")
        inside = [p for p in survey if geo.point_in_polygon(p, pts)]
        if inside:
            raise ValueError(
                f"{len(inside)} survey waypoint(s) inside exclusion '{zone['name']}': {inside[:2]}"
            )
        bad = [wp for wp in (transit or []) if geo.point_in_polygon(wp, pts)]
        if bad:
            raise ValueError(f"transit waypoint(s) inside exclusion '{zone['name']}': {bad[:2]}")
        if landing is not None and geo.point_in_polygon(landing, pts):
            raise ValueError(f"landing point {landing} is inside exclusion '{zone['name']}'")
