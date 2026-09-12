"""Acceptance rules for detections, ported from the team's outdoor FSM."""

from __future__ import annotations

import pytest

from imav_m1.config import load_config
from imav_m1.detection.filter import accept_detections, label_of
from imav_m1.mission import geo

SITE = (48.8095202, 7.8520274)


@pytest.fixture
def cfg():
    return load_config("sim")


def det(**kw):
    base = {"lat": SITE[0], "lon": SITE[1], "cls": "CCF", "conf": 0.9, "id": "veh-1"}
    base.update(kw)
    return base


def reasons(rejected):
    return [r["reason"] for r in rejected]


def test_a_good_fix_is_accepted(cfg):
    ok, bad = accept_detections([det(ident="67-CCF-M-ING", position_error_m=2.0)], cfg)
    assert len(ok) == 1 and bad == []
    assert label_of(ok[0]) == "67-CCF-M-ING"


def test_label_falls_back_to_class(cfg):
    ok, _ = accept_detections([det(ident=None)], cfg)
    assert label_of(ok[0]) == "CCF"


def test_low_confidence_is_dropped(cfg):
    ok, bad = accept_detections([det(conf=0.2)], cfg)
    assert ok == [] and "confidence" in reasons(bad)[0]


def test_a_fix_admitting_worse_than_five_metres_is_dropped(cfg):
    """The rulebook scores within 5 m (§5.4.1), so submitting a known-worse fix cannot score."""
    ok, bad = accept_detections([det(position_error_m=8.0)], cfg)
    assert ok == [] and "position error" in reasons(bad)[0]
    ok, _ = accept_detections([det(position_error_m=5.0)], cfg)
    assert len(ok) == 1, "exactly at the limit is still acceptable"


def test_unlabelled_and_unpositioned_fixes_are_dropped(cfg):
    ok, bad = accept_detections(
        [det(cls=None, ident=None), det(id="b", lat=None), det(id="c", lat="over there")], cfg
    )
    assert ok == []
    assert reasons(bad) == ["no class or identification", "no position", "position is not a number"]


def test_missing_confidence_or_error_is_not_held_against_a_detector(cfg):
    """Both fields are optional in the contract, so absence must not silently drop a vehicle."""
    ok, bad = accept_detections([{"lat": SITE[0], "lon": SITE[1], "cls": "VT4"}], cfg)
    assert len(ok) == 1 and bad == []


def test_same_id_twice_is_one_vehicle_and_keeps_the_better_fix(cfg):
    ok, bad = accept_detections(
        [det(conf=0.6, position_error_m=4.0), det(conf=0.95, position_error_m=1.0)], cfg
    )
    assert len(ok) == 1
    assert ok[0]["conf"] == 0.95, "kept the fix with the smaller position error"
    assert "duplicate" in reasons(bad)[0]


def test_same_class_close_by_is_merged_even_with_different_ids(cfg):
    """A truck seen on two survey lines gets two ids from the tracker. It is still one truck."""
    near = geo.offset(SITE, 4.0, 3.0)
    ok, bad = accept_detections(
        [det(id="a"), det(id="b", lat=near[0], lon=near[1], conf=0.95)], cfg
    )
    assert len(ok) == 1 and len(bad) == 1
    assert ok[0]["merged_from"] == ["a"] or ok[0]["merged_from"] == ["b"]


def test_two_real_vehicles_far_apart_are_both_kept(cfg):
    far = geo.offset(SITE, 60.0, 0.0)
    ok, _ = accept_detections([det(id="a"), det(id="b", lat=far[0], lon=far[1])], cfg)
    assert len(ok) == 2


def test_different_classes_at_the_same_spot_are_not_merged(cfg):
    ok, _ = accept_detections([det(id="a", cls="CCF"), det(id="b", cls="VT4")], cfg)
    assert len(ok) == 2, "two vehicle types in one place is a real answer, not a duplicate"


def test_thresholds_come_from_config(cfg):
    cfg["detection"]["accept"] = {
        "min_confidence": None,
        "max_position_error_m": None,
        "merge_radius_m": 0.0,
        "require_label": False,
    }
    ok, bad = accept_detections([det(conf=0.01, position_error_m=99.0, cls=None, ident=None)], cfg)
    assert len(ok) == 1 and bad == [], "every gate is switchable"


def test_order_is_preserved(cfg):
    a = det(id="a")
    b = det(id="b", **dict(zip(("lat", "lon"), geo.offset(SITE, 80, 0), strict=False)))
    ok, _ = accept_detections([a, b], cfg)
    assert [d["id"] for d in ok] == ["a", "b"]
