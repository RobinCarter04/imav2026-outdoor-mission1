"""Projection and pose interpolation — detection/georef.py.

The numbers here are the ones that matter for the 5 m rulebook tolerance (§5.4.1): a pixel offset
of exactly f_px must land exactly alt_m away on the ground, and the north/east sense must be right
for every heading. A rotated projection still looks plausible on a map.
"""

from __future__ import annotations

import math

import pytest

from imav_m1.detection.georef import (
    Camera,
    Pose,
    PoseBuffer,
    off_nadir_fraction,
    pixel_to_latlon,
)
from imav_m1.mission import geo

CAM = Camera(width=1456, height=1088, f_px=1000.0)
HOME = (48.806462, 7.852303)


def pose(**kw) -> Pose:
    base = dict(lat=HOME[0], lon=HOME[1], alt_m=60.0, yaw_deg=0.0)
    base.update(kw)
    return Pose(**base)


def test_centre_pixel_is_directly_below():
    fix = pixel_to_latlon(CAM.width / 2, CAM.height / 2, pose(), CAM)
    assert geo.distance_m(fix, HOME) < 0.01


def test_one_focal_length_of_offset_is_one_altitude_of_ground():
    """A pixel f_px right of centre at 60 m is 60 m east when heading north."""
    fix = pixel_to_latlon(CAM.width / 2 + CAM.f_px, CAM.height / 2, pose(), CAM)
    east, north = geo.to_local(fix[0], fix[1], HOME)
    assert east == pytest.approx(60.0, abs=0.1)
    assert north == pytest.approx(0.0, abs=0.1)


def test_image_up_is_north_when_heading_north():
    fix = pixel_to_latlon(CAM.width / 2, CAM.height / 2 - CAM.f_px, pose(), CAM)
    east, north = geo.to_local(fix[0], fix[1], HOME)
    assert north == pytest.approx(60.0, abs=0.1)
    assert east == pytest.approx(0.0, abs=0.1)


def test_image_up_is_east_when_heading_east():
    fix = pixel_to_latlon(CAM.width / 2, CAM.height / 2 - CAM.f_px, pose(yaw_deg=90.0), CAM)
    east, north = geo.to_local(fix[0], fix[1], HOME)
    assert east == pytest.approx(60.0, abs=0.1)
    assert north == pytest.approx(0.0, abs=0.1)


def test_nose_up_pitch_throws_the_fix_forward():
    """5 degrees of pitch at 60 m moves the centre pixel 5.2 m — the whole error budget."""
    fix = pixel_to_latlon(CAM.width / 2, CAM.height / 2, pose(pitch_deg=5.0), CAM)
    east, north = geo.to_local(fix[0], fix[1], HOME)
    assert north == pytest.approx(60.0 * math.tan(math.radians(5.0)), abs=0.05)
    assert east == pytest.approx(0.0, abs=0.01)


def test_right_wing_down_roll_throws_the_fix_left():
    fix = pixel_to_latlon(CAM.width / 2, CAM.height / 2, pose(roll_deg=5.0), CAM)
    east, _ = geo.to_local(fix[0], fix[1], HOME)
    assert east == pytest.approx(-60.0 * math.tan(math.radians(5.0)), abs=0.05)


def test_ray_above_the_horizon_returns_none_instead_of_a_plausible_position():
    assert pixel_to_latlon(CAM.width / 2, CAM.height / 2, pose(pitch_deg=95.0), CAM) is None


def test_no_altitude_returns_none():
    assert pixel_to_latlon(CAM.width / 2, CAM.height / 2, pose(alt_m=0.0), CAM) is None


def test_mount_yaw_offset_rotates_the_camera_in_the_airframe():
    """Camera turned 90 deg clockwise: image-up now points along the right wing."""
    fix = pixel_to_latlon(
        CAM.width / 2, CAM.height / 2 - CAM.f_px, pose(), CAM, mount_yaw_offset_deg=90.0
    )
    east, north = geo.to_local(fix[0], fix[1], HOME)
    assert east == pytest.approx(60.0, abs=0.1)
    assert north == pytest.approx(0.0, abs=0.1)


def test_camera_from_hfov_and_gsd():
    cam = Camera.from_hfov(1456, 1088, 2 * math.degrees(math.atan(1456 / 2 / 1000.0)))
    assert cam.f_px == pytest.approx(1000.0, abs=0.01)
    assert cam.gsd_m_per_px(60.0) == pytest.approx(0.06, abs=0.001)


def test_camera_from_config_refuses_to_guess_an_unknown_lens():
    cfg = {"camera": {"width": 1456, "height": 1088, "hfov_deg": None}}
    with pytest.raises(ValueError, match="hfov_deg"):
        Camera.from_config(cfg)


def test_off_nadir_fraction_centre_and_corner():
    assert off_nadir_fraction(CAM.width / 2, CAM.height / 2, CAM) == pytest.approx(0.0)
    assert off_nadir_fraction(CAM.width, CAM.height, CAM) == pytest.approx(1.0)


# ── pose buffer ───────────────────────────────────────────────────────────────────────────────


def test_pose_is_interpolated_to_the_frame_time():
    buf = PoseBuffer(max_gap_s=1.0)
    buf.add(Pose(lat=0.0, lon=0.0, alt_m=50.0, yaw_deg=0.0, t=10.0))
    buf.add(Pose(lat=0.001, lon=0.0, alt_m=60.0, yaw_deg=10.0, t=11.0))
    p = buf.at(10.5)
    assert p.lat == pytest.approx(0.0005)
    assert p.alt_m == pytest.approx(55.0)
    assert p.yaw_deg == pytest.approx(5.0)


def test_yaw_interpolates_the_short_way_round():
    buf = PoseBuffer(max_gap_s=1.0)
    buf.add(Pose(lat=0.0, lon=0.0, alt_m=50.0, yaw_deg=350.0, t=0.0))
    buf.add(Pose(lat=0.0, lon=0.0, alt_m=50.0, yaw_deg=10.0, t=1.0))
    assert buf.at(0.5).yaw_deg % 360.0 == pytest.approx(0.0, abs=1e-6)


def test_no_pose_across_a_telemetry_hole():
    buf = PoseBuffer(max_gap_s=0.5)
    buf.add(Pose(lat=0.0, lon=0.0, alt_m=50.0, yaw_deg=0.0, t=0.0))
    buf.add(Pose(lat=0.0, lon=0.0, alt_m=50.0, yaw_deg=0.0, t=10.0))
    assert buf.at(5.0) is None
    assert buf.at(0.2) is not None  # close enough to a real sample


def test_frame_before_or_after_the_telemetry_is_only_used_if_close():
    buf = PoseBuffer(max_gap_s=0.5)
    buf.add(Pose(lat=0.0, lon=0.0, alt_m=50.0, yaw_deg=0.0, t=100.0))
    assert buf.at(99.8) is not None
    assert buf.at(99.0) is None
    assert buf.at(100.2) is not None
    assert buf.at(101.0) is None


def test_empty_buffer_has_no_pose():
    assert PoseBuffer().at(0.0) is None
