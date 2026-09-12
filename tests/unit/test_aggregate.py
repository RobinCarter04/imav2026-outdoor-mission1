"""Per-frame fixes -> one row per vehicle — detection/aggregate.py and detection/geotag.py.

The failure that costs points is submitting one vehicle twice, or splitting one vehicle into two
rows; the rulebook scores per vehicle (§5.4.1). These cover both directions.
"""

from __future__ import annotations

import json

import pytest

from imav_m1.detection.aggregate import Observation, VehicleAggregator
from imav_m1.detection.filter import accept_detections
from imav_m1.detection.georef import Camera, Pose, PoseBuffer
from imav_m1.detection.geotag import observations, pixel_of, run
from imav_m1.mission import geo

HOME = (48.806462, 7.852303)
CAM = Camera(width=1456, height=1088, f_px=1000.0)
CFG = {
    "camera": {"width": 1456, "height": 1088, "f_px": 1000.0, "mount_yaw_offset_deg": 0.0},
    "detection": {"aggregate": {"link_radius_m": 8.0, "min_observations": 2}},
}


def obs_at(p, cls="CCF", conf=0.8, t=0.0, quality=0.5):
    return Observation(lat=p[0], lon=p[1], cls=cls, conf=conf, t=t, quality=quality)


def test_one_vehicle_seen_many_times_is_one_row():
    agg = VehicleAggregator(CFG)
    for i in range(6):
        agg.add(obs_at(geo.offset(HOME, 1.0 * (i % 3) - 1.0, 0.5 * i - 1.0), t=float(i)))
    rows = agg.vehicles()
    assert len(rows) == 1
    assert rows[0]["n_obs"] == 6
    assert geo.distance_m((rows[0]["lat"], rows[0]["lon"]), HOME) < 3.0


def test_two_vehicles_well_apart_are_two_rows():
    agg = VehicleAggregator(CFG)
    far = geo.offset(HOME, 50.0, 0.0)
    for i in range(3):
        agg.add(obs_at(HOME, t=float(i)))
        agg.add(obs_at(far, cls="VBL", t=float(i)))
    rows = agg.vehicles()
    assert len(rows) == 2
    assert {r["cls"] for r in rows} == {"CCF", "VBL"}
    assert [r["id"] for r in rows] == ["veh-1", "veh-2"]


def test_different_classes_in_the_same_place_stay_apart():
    agg = VehicleAggregator(CFG)
    for i in range(3):
        agg.add(obs_at(HOME, cls="CCF", t=float(i)))
        agg.add(obs_at(geo.offset(HOME, 2.0, 0.0), cls="VBL", t=float(i)))
    assert len(agg.vehicles()) == 2


def test_an_unnamed_box_joins_the_vehicle_it_sits_on():
    agg = VehicleAggregator(CFG)
    agg.add(obs_at(HOME, cls="CCF"))
    agg.add(obs_at(geo.offset(HOME, 1.0, 0.0), cls="unknown", conf=0.9))
    rows = agg.vehicles()
    assert len(rows) == 1
    assert rows[0]["cls"] == "CCF"


def test_the_majority_class_wins_a_disagreement():
    agg = VehicleAggregator(CFG)
    for _ in range(3):
        agg.add(obs_at(HOME, cls="CCF", conf=0.6))
    agg.add(obs_at(HOME, cls="VT4", conf=0.95))
    assert agg.vehicles()[0]["cls"] == "CCF"


def test_a_single_glimpse_is_reported_as_dropped_not_submitted():
    agg = VehicleAggregator(CFG)
    agg.add(obs_at(HOME))
    assert agg.vehicles() == []
    dropped = agg.dropped()
    assert len(dropped) == 1 and "needs 2" in dropped[0]["reason"]


def test_position_error_never_claims_better_than_the_floor():
    agg = VehicleAggregator(CFG)
    for i in range(5):
        agg.add(obs_at(HOME, t=float(i)))  # identical fixes: zero spread
    assert agg.vehicles()[0]["position_error_m"] == pytest.approx(3.0)


def test_position_error_grows_with_a_scattered_cluster():
    wide = {**CFG, "detection": {"aggregate": {"link_radius_m": 20.0, "min_observations": 2}}}
    agg = VehicleAggregator(wide)
    for dx in (-8.0, -4.0, 0.0, 4.0, 8.0):
        agg.add(obs_at(geo.offset(HOME, dx, 0.0)))
    assert agg.vehicles()[0]["position_error_m"] == pytest.approx(4.0, abs=0.1)


def test_rows_pass_straight_into_the_submission_filter():
    agg = VehicleAggregator(CFG)
    for i in range(4):
        agg.add(obs_at(HOME, t=float(i)))
        agg.add(obs_at(geo.offset(HOME, 40.0, 0.0), cls="VBL", t=float(i)))
    accepted, rejected = accept_detections(agg.vehicles(), CFG)
    assert len(accepted) == 2
    assert rejected == []


# ── geotag: boxes + telemetry -> rows ─────────────────────────────────────────────────────────


def test_bbox_centre_is_used_not_the_bottom_edge():
    assert pixel_of({"bbox": [100, 200, 200, 400]}, CAM) == (150.0, 300.0)


def test_boxes_from_a_resized_frame_are_scaled_back():
    px, py = pixel_of({"bbox": [0, 0, 640, 480], "frame_w": 640, "frame_h": 480}, CAM)
    assert (px, py) == pytest.approx((728.0, 544.0))


def test_a_box_with_no_telemetry_is_skipped_with_a_reason():
    poses = PoseBuffer(max_gap_s=0.5)
    poses.add(Pose(lat=HOME[0], lon=HOME[1], alt_m=60.0, yaw_deg=0.0, t=0.0))
    obs, skipped = observations([{"t": 99.0, "px": 728, "py": 544}], poses, CAM, CFG)
    assert obs == []
    assert "pose gap" in skipped[0]["reason"]


def test_a_box_with_no_timestamp_is_skipped():
    obs, skipped = observations([{"px": 1, "py": 1}], PoseBuffer(), CAM, CFG)
    assert "timestamp" in skipped[0]["reason"]


def test_end_to_end_one_pass_over_one_truck(tmp_path):
    """A truck at a known spot, seen in 5 frames as the aircraft flies north past it."""
    truck = geo.offset(HOME, 0.0, 0.0)
    run_dir = tmp_path / "flight"
    (run_dir / "detections").mkdir(parents=True)

    telem, raw = [], []
    for i in range(5):
        t = 100.0 + i * 0.5
        # Aircraft 10 m south of the truck moving north at 5 m/s, so the truck sweeps up the frame.
        drone = geo.offset(truck, 0.0, -10.0 + i * 5.0)
        telem.append(
            {
                "t": t,
                "lat": drone[0],
                "lon": drone[1],
                "alt": 60.0,
                "hdg": 0.0,
                "pitch": 0.0,
                "roll": 0.0,
            }
        )
        # Where the truck appears: north offset maps to pixels above centre.
        north_m = geo.to_local(truck[0], truck[1], drone)[1]
        py = CAM.height / 2 - north_m * CAM.f_px / 60.0
        raw.append(
            {"t": t, "bbox": [728 - 20, py - 20, 728 + 20, py + 20], "cls": "CCF", "conf": 0.9}
        )

    (run_dir / "telemetry.jsonl").write_text("\n".join(json.dumps(r) for r in telem))
    (run_dir / "detections" / "raw_detections.jsonl").write_text(
        "\n".join(json.dumps(r) for r in raw)
    )

    result = run(run_dir, CFG)
    assert result["projected"] == 5
    assert len(result["vehicles"]) == 1
    v = result["vehicles"][0]
    assert v["cls"] == "CCF"
    assert geo.distance_m((v["lat"], v["lon"]), truck) < 1.0

    written = (run_dir / "detections" / "detections.jsonl").read_text().strip().splitlines()
    assert len(written) == 1
    assert json.loads(written[0])["id"] == "veh-1"
