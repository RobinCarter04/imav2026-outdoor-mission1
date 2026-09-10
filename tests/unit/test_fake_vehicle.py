from imav_m1.mission import geo
from imav_m1.mission.items import build_survey_mission
from imav_m1.vehicle import FakeVehicle, Waypoint

HOME = (48.806567, 7.852134)


def _fly(v: FakeVehicle, seconds: int, dt: float = 1.0):
    for _ in range(int(seconds / dt)):
        v.advance(dt)


def test_guided_takeoff_then_auto_mission_to_landing():
    v = FakeVehicle(home=HOME, speed_mps=10.0)
    v.connect()
    assert v.mode() == "STABILIZE" and v.armed() is False
    assert v.set_mode("GUIDED") and v.arm(5.0)
    v.takeoff(30.0)
    _fly(v, 20)
    assert abs(v.telemetry().alt_rel_m - 30.0) < 1e-6

    a, b = geo.offset(HOME, 100, 0), geo.offset(HOME, 100, 100)
    items, first, last = build_survey_mission(
        [Waypoint(*a, 30.0), Waypoint(*b, 30.0)], 10.0, HOME, 30.0
    )
    assert (first, last) == (2, 3) and len(items) == 6
    assert v.upload_mission(items) and v.mission_count() == 6
    assert v.set_mode("AUTO")
    _fly(v, 12)
    cur, reached = v.mission_progress()
    assert reached == 2 and cur == 3
    _fly(v, 40)
    assert v.mission_progress()[1] == last + 1  # transit waypoint reached
    _fly(v, 60)
    assert v.armed() is False and v.telemetry().alt_rel_m == 0.0
    assert v.mission_progress()[1] == 5  # NAV_LAND reached
    assert geo.distance_m((v.lat, v.lon), HOME) < 1.0


def test_pilot_override_and_rtl():
    v = FakeVehicle(home=HOME)
    v.connect()
    v.set_mode("GUIDED")
    v.arm(1)
    v.takeoff(20)
    _fly(v, 10)
    v.pilot_set_mode("LOITER")
    assert v.mode() == "LOITER"
    v.set_mode("RTL")
    _fly(v, 30)
    assert v.armed() is False


def test_upload_failure_and_mode_rejection_are_reported():
    v = FakeVehicle()
    v.connect()
    v.fail_next_upload = True
    assert v.upload_mission([]) is False and v.upload_mission([]) is True
    v.reject_modes.add("AUTO")
    assert v.set_mode("AUTO") is False and v.mode() == "STABILIZE"
