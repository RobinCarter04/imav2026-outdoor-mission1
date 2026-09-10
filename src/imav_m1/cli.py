"""Command-line entry points.

imav-m1 check-config --profile sim        print the merged config
imav-m1 plan --profile sim [--kml f] [--out d]
      offline: plan the survey, write a preview SVG + summary
imav-m1 run --profile sim [--kml f] [--auto] [--no-gui] [--detector placeholder|none] [--name x]
      connect to the vehicle, start the detector process, run the state machine + dashboard.
      --auto scripts the operator (setup → preflight → pilot ready → start) for headless runs.
imav-m1 replay --profile sim              (not implemented — detection replay, WORKING_NOTES §5)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _plan(args) -> int:
    from .mapping.report import write_map_svg
    from .mission.area import load_area_inputs
    from .mission.items import build_survey_mission
    from .mission.survey import plan_survey

    cfg = load_config(args.profile)
    area = load_area_inputs(cfg, args.kml)
    plan = plan_survey(area.survey, cfg)
    landing = area.landing
    items, first, last = build_survey_mission(
        plan.waypoints, cfg["mission"]["cruise_speed_mps"], landing, cfg["mission"]["cruise_alt_m"]
    )
    out = Path(args.out or (PROJECT_ROOT / "data" / "plans"))
    out.mkdir(parents=True, exist_ok=True)
    svg = out / f"plan_{args.profile}.svg"
    write_map_svg(
        svg,
        area.survey,
        area.fence,
        [(w.lat, w.lon) for w in plan.waypoints],
        [],
        landing,
        f"Survey plan ({args.profile}) — {plan.n_lines} lines, {plan.length_m / 1000:.1f} km, ~{plan.est_time_s / 60:.1f} min",  # noqa: E501
    )
    summary = {
        "area": area.summary(),
        "plan": plan.summary(),
        "mission_items": len(items),
        "survey_seq_range": [first, last],
        "landing": landing,
        "preview": str(svg),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _run(args) -> int:
    from .detection.link import DetectorLink
    from .mission.framework import MissionContext, SharedStatus, StateMachine
    from .mission.run_meta import create_run_dir, write_run_yaml
    from .mission.states import INITIAL_STATE, STATE_CLASSES
    from .mission.telemetry_log import TelemetryLog
    from .vehicle.mavlink_vehicle import MavlinkVehicle

    cfg = load_config(args.profile)
    run_dir = create_run_dir(cfg, PROJECT_ROOT, args.name)
    write_run_yaml(run_dir, cfg, PROJECT_ROOT, sys.argv)
    print(f"[imav-m1] run dir: {run_dir}")

    status = SharedStatus()
    vehicle = MavlinkVehicle(cfg, status)
    vehicle.connect()
    detector = DetectorLink(run_dir)
    detector.set_mode("PASSIVE")
    tlog = TelemetryLog(run_dir)
    ctx = MissionContext(
        vehicle=vehicle,
        cfg=cfg,
        status=status,
        run_dir=run_dir,
        detector=detector,
        telemetry_log=tlog,
    )
    if args.kml:
        ctx.shared["kml_path"] = args.kml
    if args.auto:
        ctx.shared["stop_on_done"] = True

    det_proc = None
    if args.detector == "placeholder":
        pl = cfg.get("detection", {}).get("placeholder", {})
        det_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "imav_m1.detection.placeholder",
                "--run-dir",
                str(run_dir),
                "--targets",
                json.dumps(cfg["camera"].get("synthetic_targets") or []),
                "--radius-m",
                str(pl.get("radius_m", 40.0)),
                "--period-s",
                str(pl.get("period_s", 0.5)),
                "--noise-m",
                str(pl.get("noise_m", 0.0)),
            ]
        )
        print(f"[imav-m1] placeholder detector pid {det_proc.pid}")

    machine = StateMachine(ctx, STATE_CLASSES, INITIAL_STATE)
    sm_thread = threading.Thread(target=machine.run, daemon=True, name="state-machine")
    sm_thread.start()

    if args.auto:
        threading.Thread(
            target=_scripted_operator, args=(status, args.kml), daemon=True, name="auto-operator"
        ).start()

    ops = cfg.get("operator", {})
    exit_code = 1
    try:
        if args.no_gui:
            while sm_thread.is_alive():
                time.sleep(0.5)
        else:
            from .ops.dashboard import create_app

            app = create_app(status, run_dir)
            host, port = (
                ops.get("dashboard_host", "0.0.0.0"),
                int(args.port or ops.get("dashboard_port", 5000)),
            )
            print(f"[imav-m1] operator dashboard: http://localhost:{port}/")
            if args.auto:
                threading.Thread(
                    target=lambda: (sm_thread.join(), _shutdown_flask()), daemon=True
                ).start()
            app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        exit_code = 0 if machine.current_name == "DONE" else 1
    except KeyboardInterrupt:
        print("\n[imav-m1] stopped by user")
    finally:
        machine.stop()
        if det_proc is not None and det_proc.poll() is None:
            det_proc.terminate()
        tlog.close()
        vehicle.close()
    print(f"[imav-m1] final state: {machine.current_name}  history: {' > '.join(machine.history)}")
    return exit_code


def _shutdown_flask() -> None:
    import os
    import signal

    time.sleep(1.0)
    os.kill(os.getpid(), signal.SIGINT)


def _scripted_operator(status, kml: str | None) -> None:
    """Presses the dashboard buttons in order — the same commands a human sends (headless runs)."""

    def wait(pred, timeout):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if pred(status.get_status()):
                return True
            time.sleep(0.5)
        return False

    time.sleep(1.0)
    status.send_command({"type": "setup", "kml": kml} if kml else {"type": "setup"})
    if not wait(lambda s: s.get("idle", {}).get("mission_uploaded"), 120):
        print("[auto-operator] setup did not complete")
        return
    status.send_command({"type": "preflight"})
    status.send_command({"type": "pilot_ready", "value": True})
    status.send_command({"type": "start_mission", "when_ready": True})
    print("[auto-operator] commands sent — mission starts when preflight is green")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="imav-m1")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check-config", "plan", "run", "replay"):
        p = sub.add_parser(name)
        p.add_argument("--profile", required=True, choices=["sim", "hardware"])
        if name in ("plan", "run"):
            p.add_argument(
                "--kml", help="areas KML (Mapping Area 1 / Flight Area / Landing placemarks)"
            )
        if name == "plan":
            p.add_argument("--out", help="output dir for the preview (default data/plans)")
        if name == "run":
            p.add_argument(
                "--auto", action="store_true", help="scripted operator: setup → preflight → start"
            )
            p.add_argument("--no-gui", action="store_true")
            p.add_argument("--detector", choices=["placeholder", "none"], default="placeholder")
            p.add_argument("--name", default="mission")
            p.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    if args.cmd == "check-config":
        print(json.dumps(load_config(args.profile), indent=2, default=str))
        return 0
    if args.cmd == "plan":
        return _plan(args)
    if args.cmd == "run":
        return _run(args)
    print("[imav-m1] replay: not implemented yet (WORKING_NOTES §5)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
