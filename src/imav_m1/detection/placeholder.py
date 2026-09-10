"""Placeholder detector process — stands in for the teammate's detector during SITL work.

Runs as its own process (`python -m imav_m1.detection.placeholder --run-dir ...`), speaks only the
file contract in detection/link.py, and "detects" synthetic targets (cfg camera.synthetic_targets)
whenever the aircraft's logged pose passes within `radius_m` of one while the mode is DETECTING.
Reported position = target position + optional Gaussian noise, so georef error can be exercised.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from ..mission.geo import distance_m, offset
from .link import DetectorLink


def last_pose(telemetry_file: Path) -> dict | None:
    try:
        with open(telemetry_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4096))
            lines = f.read().decode(errors="ignore").splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            d = json.loads(line)
            if d.get("lat") is not None:
                return d
        except json.JSONDecodeError:
            continue
    return None


def run(
    run_dir: Path,
    targets: list[dict],
    radius_m: float,
    period_s: float,
    noise_m: float,
    once: bool = False,
) -> None:
    link = DetectorLink(run_dir)
    tel = run_dir / "telemetry.jsonl"
    reported: set[int] = set()
    print(
        f"[placeholder-detector] watching {run_dir} — {len(targets)} synthetic targets, radius {radius_m} m"  # noqa: E501
    )
    while True:
        mode = link.read_mode()
        if mode == "DETECTING":
            pose = last_pose(tel)
            if pose:
                here = (pose["lat"], pose["lon"])
                for i, tg in enumerate(targets):
                    if i in reported:
                        continue
                    tpos = (float(tg["lat"]), float(tg["lon"]))
                    if distance_m(here, tpos) <= radius_m:
                        lat, lon = (
                            offset(tpos, random.gauss(0, noise_m), random.gauss(0, noise_m))
                            if noise_m
                            else tpos
                        )
                        det = {
                            "t": time.time(),
                            "lat": lat,
                            "lon": lon,
                            "cls": tg.get("cls", "unknown"),
                            "ident": tg.get("ident"),
                            "conf": 0.9,
                            "image": None,
                            "id": f"synthetic-{i}",
                            "source": "placeholder",
                        }
                        link.append_detection(det)
                        reported.add(i)
                        print(
                            f"[placeholder-detector] detection {det['cls']} at {lat:.6f},{lon:.6f}"
                        )
        if once:
            return
        time.sleep(period_s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--targets", default="[]", help='JSON list of {"lat","lon","cls","ident"}')
    ap.add_argument("--radius-m", type=float, default=40.0)
    ap.add_argument("--period-s", type=float, default=0.5)
    ap.add_argument("--noise-m", type=float, default=0.0)
    a = ap.parse_args(argv)
    try:
        run(Path(a.run_dir), json.loads(a.targets), a.radius_m, a.period_s, a.noise_m)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
