"""Pixel -> ground coordinate estimation.

PORTED FROM: SaR ``robin_package/passive_watch.py`` -- ``DummyEstimator._flat_earth_estimate`` and
the tilt-compensated ray-trace inside ``DummyEstimator.add_observation``.

Three deliberate changes from the SaR original:

1. **One projection path, not two.** SaR had a flat-earth branch and a ray-trace branch, and the two
   disagree by a 90 degree rotation: flat-earth treats image-up as forward, the ray-trace feeds
   image-x in as the forward component. The ray-trace reduces exactly to flat earth at zero pitch
   and roll, so there is a single function here, on the flat-earth convention (image-up = forward,
   image-right = right).
2. **A ray that misses the ground returns None.** SaR fell back to the flat-earth estimate, which
   ignores the very tilt that caused the problem. A fix that looks valid and is not costs more than
   a missing one.
3. **Pose is interpolated to the frame time** (``PoseBuffer``). SaR read the latest MAVLink value,
   which is right for a hover and costs about a metre per 100 ms of lag at 10 m/s survey speed.

Pure functions plus one buffer; no I/O, no pymavlink. See tests/unit/test_georef.py.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from ..mission import geo

LatLon = tuple[float, float]


@dataclass(frozen=True)
class Pose:
    """Where the aircraft was when a frame was captured.

    ``alt_m`` is height above the ground *under the target*, so it is the autopilot's relative
    altitude plus any terrain offset (see ``detection.georef.terrain_offset_m``). Angles are
    degrees, ArduPilot ATTITUDE convention: yaw clockwise from north, pitch positive nose up, roll
    positive right wing down.
    """

    lat: float
    lon: float
    alt_m: float
    yaw_deg: float
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    t: float = 0.0


@dataclass(frozen=True)
class Camera:
    """Pinhole model. ``f_px`` is the focal length in pixels; everything else follows from it."""

    width: int
    height: int
    f_px: float

    @classmethod
    def from_hfov(cls, width: int, height: int, hfov_deg: float) -> Camera:
        if not 0.0 < hfov_deg < 180.0:
            raise ValueError(f"camera.hfov_deg must be between 0 and 180, got {hfov_deg}")
        return cls(width, height, (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0))

    @classmethod
    def from_config(cls, cfg: dict) -> Camera:
        cam = cfg.get("camera") or {}
        width, height = int(cam.get("width") or 0), int(cam.get("height") or 0)
        if not width or not height:
            raise ValueError("camera.width and camera.height must be set")
        if cam.get("f_px"):
            return cls(width, height, float(cam["f_px"]))
        hfov = cam.get("hfov_deg")
        if hfov is None:
            raise ValueError(
                "camera.hfov_deg is not set, so pixels cannot be turned into positions. "
                "Measure it or set camera.f_px from a calibration."
            )
        return cls.from_hfov(width, height, float(hfov))

    def gsd_m_per_px(self, alt_m: float) -> float:
        """Ground sample distance at nadir. Useful for survey spacing and sanity checks."""
        return alt_m / self.f_px


def pixel_to_latlon(
    px: float,
    py: float,
    pose: Pose,
    cam: Camera,
    mount_yaw_offset_deg: float = 0.0,
) -> LatLon | None:
    """Project one image pixel onto flat ground at ``pose.alt_m`` below the aircraft.

    ``px``/``py`` are pixel coordinates in the captured frame, origin top-left. For a nadir camera
    pass the **centre** of the bounding box: the bottom edge is the oblique-camera convention and
    biases every fix down-range. Returns None when the ray does not reach the ground -- a large
    pitch or roll can point the camera at the horizon or above it.
    """
    # Ray in camera axes, then into body FRD (forward, right, down).
    fwd = -(py - cam.height / 2.0) / cam.f_px  # image up is forward
    right = (px - cam.width / 2.0) / cam.f_px
    if mount_yaw_offset_deg:
        m = math.radians(mount_yaw_offset_deg)
        fwd, right = (
            fwd * math.cos(m) - right * math.sin(m),
            fwd * math.sin(m) + right * math.cos(m),
        )
    down = 1.0

    # Body -> NED: Rz(yaw) @ Ry(pitch) @ Rx(roll), ArduPilot Euler convention.
    roll, pitch, yaw = (
        math.radians(pose.roll_deg),
        math.radians(pose.pitch_deg),
        math.radians(pose.yaw_deg),
    )
    cr, sr = math.cos(roll), math.sin(roll)
    y1 = right * cr - down * sr
    z1 = right * sr + down * cr

    cp, sp = math.cos(pitch), math.sin(pitch)
    x2 = fwd * cp + z1 * sp
    z2 = -fwd * sp + z1 * cp

    cy, sy = math.cos(yaw), math.sin(yaw)
    north = x2 * cy - y1 * sy
    east = x2 * sy + y1 * cy
    down_ned = z2

    if down_ned <= 1e-6 or pose.alt_m <= 0.0:
        return None
    t = pose.alt_m / down_ned
    return geo.offset((pose.lat, pose.lon), east * t, north * t)


def off_nadir_fraction(px: float, py: float, cam: Camera) -> float:
    """0 at the frame centre, 1 at a corner. A cheap proxy for how much to trust a fix."""
    dx = (px - cam.width / 2.0) / (cam.width / 2.0)
    dy = (py - cam.height / 2.0) / (cam.height / 2.0)
    return min(1.0, math.hypot(dx, dy) / math.sqrt(2.0))


class PoseBuffer:
    """Timestamped poses, interpolated to a frame's capture time.

    Feed it telemetry as it arrives (or replay ``telemetry.jsonl`` offline) and ask for the pose at
    the instant a frame was taken. ``at()`` returns None rather than guessing when the nearest
    telemetry is further away than ``max_gap_s``.
    """

    def __init__(self, max_gap_s: float = 0.5):
        self.max_gap_s = float(max_gap_s)
        self._t: list[float] = []
        self._poses: list[Pose] = []

    def __len__(self) -> int:
        return len(self._poses)

    def add(self, pose: Pose) -> None:
        i = bisect.bisect_right(self._t, pose.t)
        self._t.insert(i, pose.t)
        self._poses.insert(i, pose)

    def at(self, t: float) -> Pose | None:
        if not self._poses:
            return None
        i = bisect.bisect_left(self._t, t)
        if i == 0:
            first = self._poses[0]
            return first if first.t - t <= self.max_gap_s else None
        if i == len(self._poses):
            last = self._poses[-1]
            return last if t - last.t <= self.max_gap_s else None
        before, after = self._poses[i - 1], self._poses[i]
        span = after.t - before.t
        if span <= 0.0:
            return before
        if span > self.max_gap_s:
            # A hole in the telemetry: do not invent a pose across it.
            nearest = before if (t - before.t) <= (after.t - t) else after
            return nearest if abs(nearest.t - t) <= self.max_gap_s else None
        f = (t - before.t) / span
        return Pose(
            lat=_lerp(before.lat, after.lat, f),
            lon=_lerp(before.lon, after.lon, f),
            alt_m=_lerp(before.alt_m, after.alt_m, f),
            yaw_deg=_lerp_angle(before.yaw_deg, after.yaw_deg, f),
            pitch_deg=_lerp_angle(before.pitch_deg, after.pitch_deg, f),
            roll_deg=_lerp_angle(before.roll_deg, after.roll_deg, f),
            t=t,
        )


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _lerp_angle(a: float, b: float, f: float) -> float:
    """Interpolate the short way round, so 350 deg to 10 deg passes through 0, not 180."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * f
