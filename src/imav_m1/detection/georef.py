"""Pixel → ground coordinate estimation.

PORT FROM: the GPS-estimation section of SaR robin_package/passive_watch.py (GSD projection with
optional tilt compensation). Extract only that logic; it must be a pure function of
(pixel, camera intrinsics, pose) so E-03 (georef accuracy on synthetic targets) can be unit-tested.
"""

from __future__ import annotations

from ..vehicle.interface import GeoPose


def pixel_to_latlon(
    px: float, py: float, pose: GeoPose, cam: dict, roll_deg: float = 0.0, pitch_deg: float = 0.0
) -> tuple[float, float]:
    raise NotImplementedError("port from SaR passive_watch.py GPS estimation")
