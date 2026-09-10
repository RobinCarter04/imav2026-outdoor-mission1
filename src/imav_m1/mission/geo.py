"""Small, dependency-free geodesy helpers for areas a few kilometres across.

Local tangent-plane (equirectangular) maths, accurate to well under a metre over the 440 x 600 m
competition areas. Ported from the constants in SaR pattern_generator.py (Carter).
Coordinates are (lat, lon) tuples in decimal degrees everywhere in this package.
"""

from __future__ import annotations

import math

LatLon = tuple[float, float]

EARTH_R = 6_371_000.0
M_PER_DEG_LAT = EARTH_R * math.pi / 180.0


def m_per_deg_lon(lat_deg: float) -> float:
    return M_PER_DEG_LAT * math.cos(math.radians(lat_deg))


def to_local(lat: float, lon: float, ref: LatLon) -> tuple[float, float]:
    """(lat, lon) -> (x east, y north) metres relative to `ref`."""
    return ((lon - ref[1]) * m_per_deg_lon(ref[0]), (lat - ref[0]) * M_PER_DEG_LAT)


def to_latlon(x: float, y: float, ref: LatLon) -> LatLon:
    """(x east, y north) metres relative to `ref` -> (lat, lon)."""
    return (ref[0] + y / M_PER_DEG_LAT, ref[1] + x / m_per_deg_lon(ref[0]))


def distance_m(a: LatLon, b: LatLon) -> float:
    x, y = to_local(b[0], b[1], a)
    return math.hypot(x, y)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Compass bearing from a to b, 0 = north, 90 = east."""
    x, y = to_local(b[0], b[1], a)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def offset(p: LatLon, dx_east_m: float, dy_north_m: float) -> LatLon:
    return to_latlon(dx_east_m, dy_north_m, p)


def centroid(polygon: list[LatLon]) -> LatLon:
    n = len(polygon)
    return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)


def polygon_area_m2(polygon: list[LatLon]) -> float:
    ref = centroid(polygon)
    pts = [to_local(lat, lon, ref) for lat, lon in polygon]
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def point_in_polygon(pt: LatLon, polygon: list[LatLon]) -> bool:
    """Ray casting in the local metre frame (robust to lon scaling)."""
    ref = polygon[0]
    px, py = to_local(pt[0], pt[1], ref)
    pts = [to_local(lat, lon, ref) for lat, lon in polygon]
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            x_cross = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < x_cross:
                inside = not inside
    return inside


def longest_edge_heading_deg(polygon: list[LatLon]) -> float:
    """Compass bearing (0-180) of the longest polygon edge — the natural survey line direction."""
    best_len, best_bearing = -1.0, 0.0
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        d = distance_m(a, b)
        if d > best_len:
            best_len, best_bearing = d, bearing_deg(a, b)
    return best_bearing % 180.0


def inset_polygon(polygon: list[LatLon], margin_m: float) -> list[LatLon]:
    """Shrink a CONVEX polygon by `margin_m`: every edge is moved inward along its normal.

    Keeps survey waypoints a margin inside the flight zone (the camera footprint still covers the
    edge strip). Raises ValueError if the margin swallows the polygon.
    """
    if margin_m <= 0:
        return list(polygon)
    ref = centroid(polygon)
    pts = [to_local(lat, lon, ref) for lat, lon in polygon]
    n = len(pts)
    signed = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)
    )
    sign = (
        1.0 if signed > 0 else -1.0
    )  # counter-clockwise → inward normal is to the left of each edge
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        nx, ny = -dy / length * sign, dx / length * sign
        lines.append(((x1 + nx * margin_m, y1 + ny * margin_m), (dx, dy)))
    out = []
    for i in range(len(lines)):
        (p, d1), (q, d2) = lines[i - 1], lines[i]
        det = -d1[0] * d2[1] + d2[0] * d1[1]
        if abs(det) < 1e-9:
            continue
        t = ((q[0] - p[0]) * (-d2[1]) + d2[0] * (q[1] - p[1])) / det
        out.append((p[0] + t * d1[0], p[1] + t * d1[1]))
    if len(out) < 3:
        raise ValueError(f"inset of {margin_m} m leaves no polygon")
    m = len(out)
    new_signed = sum(
        out[i][0] * out[(i + 1) % m][1] - out[(i + 1) % m][0] * out[i][1] for i in range(m)
    )
    if new_signed * signed <= 0:
        raise ValueError(f"inset of {margin_m} m is larger than the polygon")
    return [to_latlon(x, y, ref) for x, y in out]


def rectangle(
    center: LatLon, width_m: float, height_m: float, heading_deg: float = 0.0
) -> list[LatLon]:
    """Axis-aligned (heading 0: width runs east-west) rectangle, optionally rotated clockwise."""
    hw, hh = width_m / 2.0, height_m / 2.0
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    a = math.radians(-heading_deg)  # compass clockwise -> maths counter-clockwise
    out = []
    for x, y in corners:
        xr = x * math.cos(a) - y * math.sin(a)
        yr = x * math.sin(a) + y * math.cos(a)
        out.append(to_latlon(xr, yr, center))
    return out
