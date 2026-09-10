"""Mission area inputs: survey polygon(s), flight-area fence, landing point.

Sources, in priority order:
  1. a KML file (`imav-m1 run --kml file.kml`) — draw the areas in Mission Planner / Google Earth on
     the day (rulebook §5.2: corners are given on competition day), placemark names below;
  2. the merged config: `mission.survey.area_polygon`, `safety.geofence.polygon`, `landing.point`.
Fence fallback: if no flight-area polygon is given, the rulebook site geofence
(`site.geofence_corners`) is used and logged loudly — it is the hard outer limit, not the
flight area.

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


@dataclass
class AreaInputs:
    survey: list[LatLon]
    fence: list[LatLon]
    landing: LatLon | None
    survey2: list[LatLon] | None = None
    source: str = "config"
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "survey_vertices": len(self.survey),
            "survey_area_ha": round(geo.polygon_area_m2(self.survey) / 10_000.0, 2),
            "fence_vertices": len(self.fence),
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
    survey = _pairs(cfg["mission"]["survey"].get("area_polygon"))
    survey2 = _pairs(cfg["mission"]["survey"].get("area2_polygon")) or None
    fence = _pairs(cfg["safety"]["geofence"].get("polygon"))
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

    if not fence:
        fence = _pairs(cfg.get("site", {}).get("geofence_corners"))
        notes.append(
            "no flight-area polygon given — using the rulebook SITE geofence (§5.2) as the fence"
        )

    validate_area_inputs(survey, fence, landing)
    return AreaInputs(survey, fence, landing, survey2, source, notes)


def validate_area_inputs(survey: list[LatLon], fence: list[LatLon], landing: LatLon | None) -> None:
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
