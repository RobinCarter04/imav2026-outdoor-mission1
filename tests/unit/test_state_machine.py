"""End-to-end Mission 1 on the FakeVehicle: the ported state machine flies without wall time."""

from __future__ import annotations

import csv

import pytest

from imav_m1.config import load_config
from imav_m1.detection.link import DetectorLink
from imav_m1.mission import geo
from imav_m1.mission.framework import MissionContext, SharedStatus, StateMachine
from imav_m1.mission.states import INITIAL_STATE, STATE_CLASSES
from imav_m1.mission.telemetry_log import TelemetryLog
from imav_m1.vehicle import FakeVehicle

SITE = (48.806567, 7.852134)
OPERATOR_SEQUENCE = (
    {"type": "setup"},
    {"type": "preflight"},
    {"type": "pilot_ready", "value": True},
    {"type": "start_mission", "when_ready": True},
)


def make_ctx(tmp_path, *, targets=None, vehicle=None, cfg=None):
    """A mission context on the FakeVehicle.

    Pass `cfg=load_config("sim", "<site>")` to fly a real site instead of the synthetic test area.
    """
    if cfg is not None:
        return _wire(
            tmp_path,
            cfg,
            targets,
            vehicle or FakeVehicle(home=tuple(cfg["site"]["sitl_home"][:2]), speed_mps=15.0),
        )
    cfg = load_config("sim")
    cfg["mission"]["survey"]["area_polygon"] = geo.rectangle(SITE, 300, 200)
    cfg["mission"]["survey"]["spacing_m"] = 60.0
    cfg["mission"]["cruise_alt_m"] = 40.0
    cfg["camera"]["hfov_deg"] = None
    cfg["safety"]["geofence"]["polygon"] = geo.rectangle(SITE, 600, 500)
    cfg["landing"]["point"] = list(geo.offset(SITE, -200, -150))
    cfg["preflight"]["min_satellites"] = 6
    cfg["site"]["exclusions"] = []
    cfg["site"]["transit_to_survey"] = []
    cfg["site"]["transit_to_home"] = []
    return _wire(tmp_path, cfg, targets, vehicle or FakeVehicle(home=SITE, speed_mps=15.0))


def _wire(tmp_path, cfg, targets, v):
    status = SharedStatus()
    detector = DetectorLink(tmp_path)
    tlog = TelemetryLog(tmp_path, min_interval_s=0.0)
    clock = {"t": 1000.0}
    targets = targets or []
    reported = set()

    def sleep(s):
        v.advance(s)
        clock["t"] += s
        # stand-in for the external detector process: report targets the aircraft passes over
        if detector.read_mode() == "DETECTING":
            for i, tg in enumerate(targets):
                if i not in reported and geo.distance_m((v.lat, v.lon), tg[:2]) < 40:
                    detector.append_detection(
                        {
                            "t": clock["t"],
                            "lat": tg[0],
                            "lon": tg[1],
                            "cls": tg[2],
                            "ident": tg[3],
                            "conf": 0.9,
                            "source": "test",
                        }
                    )
                    reported.add(i)

    ctx = MissionContext(
        vehicle=v,
        cfg=cfg,
        status=status,
        run_dir=tmp_path,
        sleep=sleep,
        clock=lambda: clock["t"],
        detector=detector,
        telemetry_log=tlog,
    )
    ctx.shared["stop_on_done"] = True
    return ctx, v, status


def _hook_after_survey_started(ctx, status, action):
    """Wrap ctx.sleep so `action()` fires once, after the first survey line is done."""
    base_sleep = ctx.sleep
    fired = {"x": False}

    def sleep(s):
        base_sleep(s)
        st = status.get_status()
        if (
            not fired["x"]
            and st["current_state"] == "SURVEY"
            and st.get("survey", {}).get("done", 0) >= 1
        ):
            fired["x"] = True
            action()

    ctx.sleep = sleep
    return fired


def test_full_mission_from_setup_to_results(tmp_path):
    targets = [
        (*geo.offset(SITE, -60, 40), "CCF", "67-CCF-M-ING"),
        (*geo.offset(SITE, 80, -50), "VT4", None),
    ]
    ctx, v, status = make_ctx(tmp_path, targets=targets)
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    final = m.run()

    assert final == "DONE", m.history
    assert m.history[:5] == ["IDLE", "GENERATE_PATTERN", "UPLOAD_FENCE", "UPLOAD_MISSION", "IDLE"]
    assert m.history[5:] == [
        "PREFLIGHT_CHECK",
        "TAKEOFF",
        "SURVEY",
        "RETURN_LAND",
        "REPORT",
        "DONE",
    ]
    assert v.armed() is False and v.telemetry().alt_rel_m == 0.0
    assert geo.distance_m((v.lat, v.lon), tuple(ctx.cfg["landing"]["point"])) < 2.0
    assert v.params["FENCE_ENABLE"] == 1.0 and v.params["FENCE_ALT_MAX"] == 75.0
    assert v.params["FENCE_ACTION"] == 2.0
    assert "mode:GUIDED" in v.calls and "arm" in v.calls and "mode:AUTO" in v.calls

    res = ctx.shared["results"]["paths"]
    with open(res["table"]) as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Vehicle Identification", "GPS coordinates"]
    assert len(rows) == 3 and {r[0] for r in rows[1:]} == {"67-CCF-M-ING", "VT4"}
    assert " ; " in rows[1][1]
    assert (tmp_path / "results" / "mission1_map.svg").read_text().startswith("<svg")
    assert (tmp_path / "results.zip").exists()
    assert ctx.detector.read_mode() == "PASSIVE"
    assert len(ctx.telemetry_log.track()) > 20
    s = status.get_status()
    assert s["results"]["detections"] == 2 and s["survey"]["pct"] == 100


def test_pilot_override_needs_handback_then_operator_resume(tmp_path):
    """Two gates: the pilot returns to GUIDED, and only then does an operator RESUME restart it."""
    ctx, v, status = make_ctx(tmp_path)
    ctx.cfg["operator"]["override_timeout_s"] = 120
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)

    st = {"phase": 0, "t": 0.0, "calls": 0}
    base_sleep = ctx.sleep

    def sleep(s):
        base_sleep(s)
        cur = status.get_status()
        elapsed = ctx.clock() - st["t"]
        if (
            st["phase"] == 0
            and cur["current_state"] == "SURVEY"
            and cur.get("survey", {}).get("done", 0) >= 1
        ):
            v.pilot_set_mode("LOITER")  # safety pilot takes over
            st.update(phase=1, t=ctx.clock(), calls=len(v.calls))
        elif st["phase"] == 1 and elapsed > 4:
            # RESUME pressed while the pilot still holds it — must be refused
            status.send_command({"type": "resume"})
            st.update(phase=2, t=ctx.clock())
        elif st["phase"] == 2 and elapsed > 4:
            assert len(v.calls) == st["calls"], (
                f"commanded the vehicle while paused: {v.calls[st['calls'] :]}"
            )
            assert status.get_status()["override"]["can_resume"] is False
            v.pilot_set_mode("GUIDED")  # pilot hands back
            st.update(phase=3, t=ctx.clock())
        elif st["phase"] == 3 and elapsed > 6:
            # handed back, but nobody pressed RESUME — the mission must still be sitting still
            assert len(v.calls) == st["calls"], "resumed without an operator RESUME"
            assert status.get_status()["override"]["can_resume"] is True
            status.send_command({"type": "resume"})
            st.update(phase=4, t=ctx.clock())

    ctx.sleep = sleep
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    assert m.run() == "DONE", m.history
    assert st["phase"] == 4, "the override sequence did not run"
    assert "ABORT" not in m.history
    assert v.calls.count("mode:AUTO") >= 2  # takeoff hand-off, then the operator-approved resume
    assert v.armed() is False


def test_override_without_operator_resume_times_out_without_commanding(tmp_path):
    ctx, v, status = make_ctx(tmp_path)
    ctx.cfg["operator"]["override_timeout_s"] = 20
    ctx.cfg["landing"]["timeout_s"] = 10  # so ABORT gives up quickly instead of waiting to disarm
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)
    st = {"phase": 0, "t": 0.0, "calls": 0}
    base_sleep = ctx.sleep

    def sleep(s):
        base_sleep(s)
        cur = status.get_status()
        if (
            st["phase"] == 0
            and cur["current_state"] == "SURVEY"
            and cur.get("survey", {}).get("done", 0) >= 1
        ):
            v.pilot_set_mode("LOITER")
            st.update(phase=1, t=ctx.clock(), calls=len(v.calls))
        elif st["phase"] == 1 and ctx.clock() - st["t"] > 5:
            v.pilot_set_mode("GUIDED")  # hands back, but no operator ever presses RESUME
            st.update(phase=2)

    ctx.sleep = sleep
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    assert m.run() == "DONE", m.history
    assert "ABORT" in m.history
    assert "override timeout" in ctx.shared["abort_reason"]
    assert v.calls.count("mode:AUTO") == 1, "re-armed autonomy without an operator"
    assert "mode:RTL" not in v.calls, "commanded RTL while the pilot had control"


def test_pilot_recovery_mode_during_override_aborts_silently(tmp_path):
    ctx, v, status = make_ctx(tmp_path)
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)
    st = {"phase": 0, "t": 0.0}
    base_sleep = ctx.sleep

    def sleep(s):
        base_sleep(s)
        cur = status.get_status()
        if (
            st["phase"] == 0
            and cur["current_state"] == "SURVEY"
            and cur.get("survey", {}).get("done", 0) >= 1
        ):
            v.pilot_set_mode("LOITER")
            st.update(phase=1, t=ctx.clock())
        elif st["phase"] == 1 and ctx.clock() - st["t"] > 4:
            v.pilot_set_mode("RTL")  # pilot decides to bring it home instead
            st.update(phase=2)

    ctx.sleep = sleep
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    assert m.run() == "DONE"
    assert "ABORT" in m.history and "RTL" in ctx.shared["abort_reason"]
    assert v.calls.count("mode:RTL") == 0  # the pilot chose it; we never sent it


def test_operator_abort_goes_rtl_then_reports(tmp_path):
    ctx, v, status = make_ctx(tmp_path)
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)
    _hook_after_survey_started(ctx, status, lambda: status.send_command({"type": "abort"}))
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    assert m.run() == "DONE"
    assert "ABORT" in m.history and m.history[-2:] == ["REPORT", "DONE"]
    assert "mode:RTL" in v.calls and v.armed() is False
    assert geo.distance_m((v.lat, v.lon), SITE) < 2.0  # RTL home
    assert ctx.shared["abort_reason"] == "operator abort"


def test_failsafe_mode_change_is_not_fought(tmp_path):
    ctx, v, status = make_ctx(tmp_path)
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)
    _hook_after_survey_started(
        ctx, status, lambda: v.pilot_set_mode("RTL")
    )  # e.g. battery failsafe
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    assert m.run() == "DONE" and "ABORT" in m.history
    assert v.calls.count("mode:RTL") == 0  # we never commanded it
    assert "failsafe" in ctx.shared["abort_reason"]


def test_preflight_rejected_when_upload_failed(tmp_path):
    ctx, v, status = make_ctx(tmp_path)
    v.connect()
    v.fail_next_upload = True
    status.send_command({"type": "setup"})
    status.send_command({"type": "preflight"})  # must be rejected: nothing uploaded
    base_sleep = ctx.sleep

    def sleep(s):
        base_sleep(s)
        if ctx.shared.get("last_error"):
            ctx.shared["_stop"] = True  # IDLE would otherwise wait forever

    ctx.sleep = sleep
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE)
    m.run()
    assert m.history == ["IDLE", "GENERATE_PATTERN", "UPLOAD_FENCE", "UPLOAD_MISSION", "IDLE"]
    assert ctx.shared["mission_uploaded"] is False
    assert "not uploaded" in (ctx.shared.get("last_error") or "")


@pytest.mark.parametrize("cmd", ["start_mission", "abort"])
def test_idle_ignores_flight_commands(tmp_path, cmd):
    ctx, v, status = make_ctx(tmp_path)
    v.connect()
    status.send_command({"type": cmd})
    status.send_command({"type": "reset"})
    ticks = {"n": 0}
    base_sleep = ctx.sleep

    def sleep(s):
        base_sleep(s)
        ticks["n"] += 1
        if ticks["n"] > 4:
            ctx.shared["_stop"] = True

    ctx.sleep = sleep
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE)
    m.run()
    assert v.armed() is False and "arm" not in v.calls


# ── site switch: Fenswood Farm, with its SSSI exclusion zone and transit corridors ─────────────


def test_fenswood_site_avoids_the_sssi_and_uploads_it_as_an_exclusion(tmp_path):
    """The Fenswood test flight: corridors around the protected zone, tighter ceiling, RTL on breach."""  # noqa: E501
    cfg = load_config("sim", "fenswood")
    ctx, v, status = make_ctx(tmp_path, cfg=cfg)
    v.connect()
    for c in OPERATOR_SEQUENCE:
        status.send_command(c)
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE, max_transitions=60)
    assert m.run() == "DONE", m.history
    assert "ABORT" not in m.history

    # the site's own limits reached the autopilot, not the global ones
    assert v.params["FENCE_ALT_MAX"] == 50.0, "site ceiling did not override the 75 m cap"
    assert v.params["FENCE_ACTION"] == 1.0, "expected RTL on breach at Fenswood, not LAND"

    # flight area + SSSI went up together, in one transaction
    kinds = [(f.kind, f.label) for f in v.fences]
    assert kinds == [("inclusion", "Flight area"), ("exclusion", "SSSI")]

    # and the aircraft never actually entered the protected zone
    sssi = [tuple(p) for p in cfg["site"]["exclusions"][0]["points"]]
    track = ctx.telemetry_log.track()
    intrusions = [p for p in track if geo.point_in_polygon(p, sssi)]
    assert not intrusions, f"{len(intrusions)} track points inside the SSSI, e.g. {intrusions[:2]}"
    assert len(track) > 30
    assert v.armed() is False
    assert geo.distance_m((v.lat, v.lon), tuple(cfg["landing"]["point"])) < 3.0


def test_planning_above_the_site_ceiling_is_refused(tmp_path):
    cfg = load_config("sim", "fenswood")
    cfg["mission"]["cruise_alt_m"] = 70.0  # legal at Haguenau, over the 50 m Fenswood ceiling
    ctx, v, status = make_ctx(tmp_path, cfg=cfg)
    v.connect()
    status.send_command({"type": "setup"})
    base_sleep = ctx.sleep

    def sleep(s):
        base_sleep(s)
        if ctx.shared.get("last_error"):
            ctx.shared["_stop"] = True

    ctx.sleep = sleep
    m = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE)
    m.run()
    assert "above the 50 m ceiling" in ctx.shared["last_error"]
    assert "arm" not in v.calls
