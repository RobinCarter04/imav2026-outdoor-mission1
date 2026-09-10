"""Survey (lawnmower) planning over an arbitrary polygon.

PORTED FROM: SaR sarFlightDay4/pattern_generator.py `generate_lawnmower` (Carter's scanline-clip
boustrophedon). Generalised: no hard-coded coordinates, no fixed UTM zone, line spacing derived from
the camera footprint and required side overlap, scan heading chosen automatically along the longest
edge. Pure geometry — no MAVLink, no I/O — so it is unit-tested directly (E-01, E-06).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..vehicle.interface import Waypoint
from . import geo
from .geo import LatLon


@dataclass
class SurveyPlan:
    waypoints: list[Waypoint]
    spacing_m: float
    heading_deg: float  # compass bearing of the scan lines
    n_lines: int
    length_m: float  # total path length including cross-overs
    est_time_s: float
    footprint_w_m: float | None
    gsd_cm_px: float | None
    polygon: list[LatLon] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "waypoints": len(self.waypoints),
            "lines": self.n_lines,
            "spacing_m": round(self.spacing_m, 1),
            "heading_deg": round(self.heading_deg, 1),
            "length_km": round(self.length_m / 1000.0, 2),
            "est_time_min": round(self.est_time_s / 60.0, 1),
            "footprint_w_m": None if self.footprint_w_m is None else round(self.footprint_w_m, 1),
            "gsd_cm_px": None if self.gsd_cm_px is None else round(self.gsd_cm_px, 2),
        }


# ── camera geometry ───────────────────────────────────────────────────────────────────────────


def footprint_m(hfov_deg: float, alt_m: float, aspect: float) -> tuple[float, float]:
    """(width, height) of the ground footprint of a nadir camera. aspect = width_px / height_px."""
    w = 2.0 * alt_m * math.tan(math.radians(hfov_deg / 2.0))
    return w, w / aspect


def line_spacing_m(footprint_width_m: float, overlap_side: float) -> float:
    if not 0.0 <= overlap_side < 1.0:
        raise ValueError("overlap_side must be in [0, 1)")
    return footprint_width_m * (1.0 - overlap_side)


# ── scanline boustrophedon ────────────────────────────────────────────────────────────────────


def _segment_intersect_y(p1, p2, y):
    (x1, y1), (x2, y2) = p1, p2
    if (y1 - y) * (y2 - y) > 0:
        return None
    if abs(y2 - y1) < 1e-12:
        return None
    t = (y - y1) / (y2 - y1)
    if t < 0.0 or t > 1.0:
        return None
    return x1 + t * (x2 - x1)


def _clip_scanline(poly_xy, y):
    xs = []
    n = len(poly_xy)
    for i in range(n):
        x = _segment_intersect_y(poly_xy[i], poly_xy[(i + 1) % n], y)
        if x is not None:
            xs.append(x)
    xs.sort()
    # de-duplicate vertex hits (a scanline through a vertex intersects two edges at the same x)
    out: list[float] = []
    for x in xs:
        if not out or abs(x - out[-1]) > 1e-6:
            out.append(x)
    return out


def _rotate(points, angle_deg):
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def lawnmower(
    polygon: list[LatLon],
    spacing_m: float,
    alt_m: float,
    heading_deg: float | None = None,
) -> tuple[list[Waypoint], float, int]:
    """Serpentine coverage of `polygon` with parallel lines `spacing_m` apart.

    heading_deg: compass bearing of the scan lines (0 = north-south lines, 90 = east-west).
    None = along the longest polygon edge (fewest turns for a rectangle).
    Returns (waypoints, heading_used, n_lines).
    """
    if len(polygon) < 3:
        raise ValueError(f"polygon needs >= 3 vertices, got {len(polygon)}")
    if spacing_m <= 0:
        raise ValueError("spacing_m must be > 0")
    if heading_deg is None:
        heading_deg = geo.longest_edge_heading_deg(polygon)

    ref = geo.centroid(polygon)
    poly_m = [geo.to_local(lat, lon, ref) for lat, lon in polygon]
    math_angle = 90.0 - heading_deg  # compass -> maths (CCW from +x east)
    poly_rot = _rotate(poly_m, -math_angle)  # scan lines become horizontal

    ys = [p[1] for p in poly_rot]
    y_min, y_max = min(ys), max(ys)
    extent = y_max - y_min
    if extent <= spacing_m:
        levels = [(y_min + y_max) / 2.0]
    else:
        levels = []
        y = y_min + spacing_m / 2.0
        while y < y_max - 1e-9:
            levels.append(y)
            y += spacing_m
        if y_max - levels[-1] > spacing_m / 2.0 + 1e-6:  # keep coverage to the far edge
            levels.append(y_max - spacing_m / 2.0)

    segments = []
    for y in levels:
        xs = _clip_scanline(poly_rot, y)
        for k in range(0, len(xs) - 1, 2):
            segments.append((xs[k], y, xs[k + 1], y))
    if not segments:
        raise ValueError("no scan lines generated — polygon degenerate for this spacing")

    pts_rot = []
    for i, (x1, y1, x2, y2) in enumerate(segments):
        pts_rot += [(x1, y1), (x2, y2)] if i % 2 == 0 else [(x2, y2), (x1, y1)]

    pts_m = _rotate(pts_rot, math_angle)
    waypoints = [Waypoint(*geo.to_latlon(x, y, ref), float(alt_m)) for x, y in pts_m]
    return waypoints, heading_deg % 180.0, len(segments)


def path_length_m(waypoints: list[Waypoint]) -> float:
    return sum(
        geo.distance_m((a.lat, a.lon), (b.lat, b.lon))
        for a, b in zip(waypoints, waypoints[1:], strict=False)
    )


# ── config-driven entry point ─────────────────────────────────────────────────────────────────


def plan_survey(polygon: list[LatLon], cfg: dict[str, Any]) -> SurveyPlan:
    """Build the survey from the merged config: altitude, overlap, camera FOV, speed."""
    m = cfg["mission"]
    cam = cfg["camera"]
    alt = float(m["cruise_alt_m"])
    sv = m["survey"]

    footprint_w = gsd = None
    hfov = cam.get("hfov_deg")
    if hfov:
        footprint_w, _ = footprint_m(float(hfov), alt, cam["width"] / cam["height"])
        gsd = footprint_w / cam["width"] * 100.0
        spacing = line_spacing_m(footprint_w, float(sv["overlap_side"]))
    elif sv.get("spacing_m"):
        spacing = float(sv["spacing_m"])
    else:
        raise ValueError(
            "need camera.hfov_deg or mission.survey.spacing_m to size the survey lines"
        )

    heading = sv.get("entry_heading_deg")
    wps, heading_used, n_lines = lawnmower(polygon, spacing, alt, heading)
    length = path_length_m(wps)
    speed = float(m["cruise_speed_mps"])
    turn_s = float(sv.get("turn_time_s", 4.0))
    est = length / speed + max(0, n_lines - 1) * turn_s
    return SurveyPlan(
        wps, spacing, heading_used, n_lines, length, est, footprint_w, gsd, list(polygon)
    )
