#!/usr/bin/env python3
"""Survey coverage / flight-time / GSD calculator for Outdoor Mission 1.

Areas from rulebook V4 §5.4.1: Mapping Area 1 = 440 x 280 m; Area 2 adds 440 x 320 m.
"Area 1+2" below ASSUMES the two are adjacent (440 x 600 m) — confirm on the day.
Assumes a nadir IMX296 (1456 px wide), survey lines flown along the 440 m axis.

Usage:
  tools/coverage_calc.py                       # default sweep, plain text
  tools/coverage_calc.py --hfov 45 --alt 60 75 --overlap 0.3 0.5 --speed 10 --markdown
Replace --hfov with the calibrated horizontal FOV as soon as it is known (docs/HARDWARE.md).
"""

from __future__ import annotations

import argparse
import math

AREAS = {"Area 1": (440.0, 280.0), "Area 1+2": (440.0, 600.0)}
PX_WIDTH = 1456


def plan(hfov_deg, alt_m, overlap, speed_mps, turn_s, along_m, across_m):
    footprint_w = 2 * alt_m * math.tan(math.radians(hfov_deg / 2))
    gsd_cm = footprint_w / PX_WIDTH * 100
    spacing = footprint_w * (1 - overlap)
    lines = math.ceil(across_m / spacing) + 1
    path_m = lines * along_m + (lines - 1) * spacing
    time_s = path_m / speed_mps + (lines - 1) * turn_s
    return footprint_w, gsd_cm, spacing, lines, path_m / 1000, time_s / 60


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--hfov", nargs="+", type=float, default=[45.0, 65.0], help="horizontal FOV, deg"
    )
    ap.add_argument(
        "--alt", nargs="+", type=float, default=[40.0, 60.0, 75.0], help="altitude AGL, m"
    )
    ap.add_argument(
        "--overlap", nargs="+", type=float, default=[0.3, 0.5, 0.65], help="side overlap"
    )
    ap.add_argument("--speed", type=float, default=10.0, help="ground speed, m/s")
    ap.add_argument("--turn-s", type=float, default=4.0, help="seconds lost per line turn")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args()

    header = (
        "HFOV°",
        "alt m",
        "side ov",
        "area",
        "footprint m",
        "GSD cm/px",
        "spacing m",
        "lines",
        "path km",
        f"min @{a.speed:.0f} m/s",
    )
    rows = []
    for hfov in a.hfov:
        for alt in a.alt:
            for ov in a.overlap:
                for name, (along, across) in AREAS.items():
                    rows.append(
                        (hfov, alt, ov, name)
                        + plan(hfov, alt, ov, a.speed, a.turn_s, along, across)
                    )

    if a.markdown:
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        fmt = (
            "| {:.0f} | {:.0f} | {:.2f} | {} | {:.0f} | {:.1f} | {:.0f} | {:d} | {:.1f} | {:.1f} |"
        )
    else:
        print("{:>6} {:>6} {:>8} {:>9} {:>12} {:>10} {:>10} {:>6} {:>8} {:>12}".format(*header))
        fmt = "{:6.0f} {:6.0f} {:8.2f} {:>9} {:12.0f} {:10.1f} {:10.0f} {:6d} {:8.1f} {:12.1f}"
    for r in rows:
        print(fmt.format(*r))


if __name__ == "__main__":
    main()
