import math

import pytest

from imav_m1.mission import geo
from imav_m1.mission.survey import (
    footprint_m,
    lawnmower,
    line_spacing_m,
    path_length_m,
    plan_survey,
)

HAGUENAU = (48.806567, 7.852134)


def test_local_roundtrip_and_distance():
    p = geo.offset(HAGUENAU, 300.0, -120.0)
    x, y = geo.to_local(p[0], p[1], HAGUENAU)
    assert abs(x - 300.0) < 0.01 and abs(y + 120.0) < 0.01
    assert abs(geo.distance_m(HAGUENAU, p) - math.hypot(300, 120)) < 0.05
    assert abs(geo.bearing_deg(HAGUENAU, geo.offset(HAGUENAU, 0, 100)) - 0.0) < 1e-6
    assert abs(geo.bearing_deg(HAGUENAU, geo.offset(HAGUENAU, 100, 0)) - 90.0) < 1e-6


def test_rectangle_area_and_containment():
    rect = geo.rectangle(HAGUENAU, 440.0, 280.0)
    assert abs(geo.polygon_area_m2(rect) - 440 * 280) < 5.0
    assert geo.point_in_polygon(HAGUENAU, rect)
    assert not geo.point_in_polygon(geo.offset(HAGUENAU, 300, 0), rect)
    assert abs(geo.longest_edge_heading_deg(rect) - 90.0) < 1e-6  # long side runs east-west


def test_footprint_and_spacing():
    w, h = footprint_m(45.0, 60.0, 1456 / 1088)
    assert abs(w - 2 * 60 * math.tan(math.radians(22.5))) < 1e-9
    assert h < w
    assert line_spacing_m(50.0, 0.4) == 30.0


def test_lawnmower_covers_rectangle_along_long_side():
    rect = geo.rectangle(HAGUENAU, 440.0, 280.0)
    wps, heading, n_lines = lawnmower(rect, spacing_m=40.0, alt_m=60.0)
    assert abs(heading - 90.0) < 1e-6  # lines east-west (along 440 m)
    assert n_lines == math.ceil(280 / 40) + 1 or n_lines == math.ceil(280 / 40)
    assert len(wps) == 2 * n_lines
    for wp in wps:  # every waypoint on/inside the polygon
        assert geo.point_in_polygon((wp.lat, wp.lon), geo.rectangle(HAGUENAU, 442.0, 282.0))
        assert wp.alt_m == 60.0
    # serpentine: consecutive line ends alternate sides
    xs = [geo.to_local(w.lat, w.lon, HAGUENAU)[0] for w in wps]
    assert xs[0] < xs[1] and xs[2] > xs[3]
    # each line spans (almost) the full 440 m
    assert abs(abs(xs[1] - xs[0]) - 440.0) < 1.0
    assert path_length_m(wps) > n_lines * 440.0


def test_lawnmower_rotated_polygon_and_explicit_heading():
    rect = geo.rectangle(HAGUENAU, 300.0, 200.0, heading_deg=30.0)
    wps, heading, n_lines = lawnmower(rect, spacing_m=50.0, alt_m=50.0)
    assert abs((heading - 120.0 + 90) % 180 - 90) < 0.5 or abs(heading - 120.0) < 0.5
    wps2, heading2, n2 = lawnmower(rect, spacing_m=50.0, alt_m=50.0, heading_deg=0.0)
    assert heading2 == 0.0 and n2 > n_lines  # across the short direction = more lines


def test_lawnmower_rejects_bad_input():
    import pytest

    with pytest.raises(ValueError):
        lawnmower([HAGUENAU, HAGUENAU], 10.0, 30.0)
    with pytest.raises(ValueError):
        lawnmower(geo.rectangle(HAGUENAU, 100, 100), 0.0, 30.0)


def test_plan_survey_from_config_uses_fov_when_known(sim_cfg):
    rect = geo.rectangle(HAGUENAU, 440.0, 280.0)
    cfg = dict(sim_cfg)
    cfg["camera"] = dict(sim_cfg["camera"], hfov_deg=45.0)
    cfg["mission"] = dict(sim_cfg["mission"], cruise_alt_m=60.0, cruise_speed_mps=10.0)
    plan = plan_survey(rect, cfg)
    assert plan.footprint_w_m and plan.gsd_cm_px
    assert plan.spacing_m == plan.footprint_w_m * (1 - cfg["mission"]["survey"]["overlap_side"])
    s = plan.summary()
    assert s["lines"] == plan.n_lines and s["est_time_min"] > 0


def test_plan_survey_falls_back_to_explicit_spacing(sim_cfg):
    rect = geo.rectangle(HAGUENAU, 440.0, 280.0)
    cfg = dict(sim_cfg)
    cfg["camera"] = dict(sim_cfg["camera"], hfov_deg=None)
    cfg["mission"] = dict(
        sim_cfg["mission"], survey=dict(sim_cfg["mission"]["survey"], spacing_m=35.0)
    )
    plan = plan_survey(rect, cfg)
    assert plan.spacing_m == 35.0 and plan.footprint_w_m is None


def test_inset_polygon_shrinks_convex_polygon_by_margin():
    rect = geo.rectangle(HAGUENAU, 440.0, 280.0, heading_deg=25.0)
    inner = geo.inset_polygon(rect, 10.0)
    assert len(inner) == 4
    assert abs(geo.polygon_area_m2(inner) - 420 * 260) < 20.0
    for p in inner:
        assert geo.point_in_polygon(p, rect)
    assert geo.inset_polygon(rect, 0.0) == rect
    with pytest.raises(ValueError):
        geo.inset_polygon(rect, 200.0)


def test_build_survey_mission_wraps_the_survey_in_transit_corridors():
    from imav_m1.mission.items import build_survey_mission
    from imav_m1.vehicle.interface import (
        MAV_CMD_DO_CHANGE_SPEED,
        MAV_CMD_NAV_LAND,
        MAV_CMD_NAV_WAYPOINT,
        Waypoint,
    )

    survey = [Waypoint(*geo.offset(HAGUENAU, 0, d), 30.0) for d in (0, 50, 100)]
    out = [geo.offset(HAGUENAU, -100, -100), geo.offset(HAGUENAU, -50, -50)]
    home = [geo.offset(HAGUENAU, -50, -50), geo.offset(HAGUENAU, -100, -100)]
    landing = geo.offset(HAGUENAU, -120, -120)

    items, first, last = build_survey_mission(
        survey,
        4.0,
        landing,
        30.0,
        transit_to_survey=out,
        transit_to_home=home,
        transit_speed_mps=8.0,
    )
    kinds = [it.command for it in items]
    assert [it.seq for it in items] == list(range(len(items)))
    assert kinds[0] == MAV_CMD_NAV_WAYPOINT and kinds[-1] == MAV_CMD_NAV_LAND
    speeds = [(it.seq, it.p2) for it in items if it.command == MAV_CMD_DO_CHANGE_SPEED]
    assert [s for _, s in speeds] == [8.0, 4.0, 8.0]  # transit, survey, transit home
    assert speeds[0][0] == 1 and speeds[1][0] == first - 1
    assert last - first + 1 == len(survey)
    survey_pts = [(items[s].lat, items[s].lon) for s in range(first, last + 1)]
    assert survey_pts == [(w.lat, w.lon) for w in survey]
    assert (items[-1].lat, items[-1].lon) == landing


def test_build_survey_mission_without_corridors_is_unchanged():
    from imav_m1.mission.items import build_survey_mission
    from imav_m1.vehicle.interface import MAV_CMD_DO_CHANGE_SPEED, Waypoint

    survey = [Waypoint(*geo.offset(HAGUENAU, 0, d), 30.0) for d in (0, 50)]
    items, first, last = build_survey_mission(survey, 5.0, HAGUENAU, 30.0)
    assert (first, last) == (2, 3)
    assert sum(1 for it in items if it.command == MAV_CMD_DO_CHANGE_SPEED) == 1
