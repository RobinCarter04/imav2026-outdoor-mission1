"""Deliverables writer — the "collate and share" step of Mission 1 (rulebook §5.4.1, Tab. 6).

results/mission1_vehicles.csv   Vehicle Identification | GPS coordinates ("lat ; lon", decimal deg)
results/mission1_map.svg        placeholder map: polygon, fence, flown track, detections, landing.
                                To be replaced by the orthomosaic / tiles from pose-tagged images.
results/summary.json            everything machine-readable (timings, plan, detections)
results.zip                     one file to hand over / copy to USB
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import zipfile
from pathlib import Path
from typing import Any

from ..detection.filter import accept_detections, label_of
from ..mission import geo


def write_vehicle_table(path: Path, detections: list[dict[str, Any]]) -> int:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Vehicle Identification", "GPS coordinates"])
        n = 0
        for d in detections:
            w.writerow([label_of(d), f"{float(d['lat']):.7f} ; {float(d['lon']):.7f}"])
            n += 1
    return n


def write_map_svg(path: Path, polygon, fence, track, detections, landing, title: str) -> None:
    pts_all = (
        list(polygon)
        + list(fence)
        + list(track)
        + [(d["lat"], d["lon"]) for d in detections if d.get("lat")]
    )
    if landing:
        pts_all.append(tuple(landing))
    if not pts_all:
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50"><text x="10" y="30">no data</text></svg>'  # noqa: E501
        )
        return
    ref = geo.centroid(pts_all)
    loc = [geo.to_local(a, b, ref) for a, b in pts_all]
    xs, ys = [p[0] for p in loc], [p[1] for p in loc]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span = max(x1 - x0, y1 - y0, 50.0)
    width, margin = 1000.0, 60.0
    scale = (width - 2 * margin) / span
    height = (y1 - y0) * scale + 2 * margin + 40

    def P(latlon):
        x, y = geo.to_local(latlon[0], latlon[1], ref)
        return f"{(x - x0) * scale + margin:.1f},{height - 40 - ((y - y0) * scale + margin):.1f}"

    def poly(pts, style):
        return (
            f'<polygon points="{" ".join(P(p) for p in pts)}" style="{style}"/>'
            if len(pts) >= 3
            else ""
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="sans-serif" font-size="12">',
        '<rect width="100%" height="100%" fill="white"/>',
        poly(fence, "fill:none;stroke:#888;stroke-width:2;stroke-dasharray:8 6"),
        poly(polygon, "fill:#1f77b41a;stroke:#1f77b4;stroke-width:2"),
    ]
    if len(track) >= 2:
        parts.append(
            f'<polyline points="{" ".join(P(p) for p in track)}" style="fill:none;stroke:#ff7f0e;stroke-width:1.5"/>'  # noqa: E501
        )
    if landing:
        parts.append(
            f'<g transform="translate({P(landing)})"><rect x="-6" y="-6" width="12" height="12" fill="#2ca02c"/>'  # noqa: E501
            f'<text x="9" y="4">landing</text></g>'
        )
    for i, d in enumerate(detections, 1):
        if d.get("lat") is None:
            continue
        label = d.get("ident") or d.get("cls") or "?"
        parts.append(
            f'<g transform="translate({P((d["lat"], d["lon"]))})"><circle r="7" fill="#d62728" stroke="white" stroke-width="2"/>'  # noqa: E501
            f'<text x="10" y="4" font-weight="bold">{i}: {label}</text></g>'
        )
    # scale bar (100 m) + north arrow + title
    bar = 100.0 * scale
    parts.append(
        f'<line x1="{margin}" y1="{height - 20}" x2="{margin + bar:.1f}" y2="{height - 20}" stroke="black" stroke-width="3"/>'  # noqa: E501
        f'<text x="{margin}" y="{height - 26}">100 m</text>'
    )
    parts.append(
        f'<g transform="translate({width - 40},{margin})"><polygon points="0,-20 -7,5 7,5" fill="black"/><text x="-4" y="22">N</text></g>'  # noqa: E501
    )
    parts.append(f'<text x="{margin}" y="24" font-size="16" font-weight="bold">{title}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(p for p in parts if p))


def collate(
    run_dir: Path,
    cfg: dict[str, Any],
    shared: dict[str, Any],
    detections: list[dict[str, Any]],
    track: list[tuple[float, float]],
    landed_time: float,
) -> dict[str, str]:
    run_dir = Path(run_dir)
    out = run_dir / "results"
    out.mkdir(exist_ok=True)
    geom = shared.get("plan_geometry") or {}
    stamp = dt.datetime.fromtimestamp(landed_time).strftime("%Y-%m-%d %H:%M:%S")
    accepted, rejected = accept_detections(detections, cfg)
    n = write_vehicle_table(out / "mission1_vehicles.csv", accepted)
    write_map_svg(
        out / "mission1_map.svg",
        [tuple(p) for p in geom.get("polygon", [])],
        [tuple(p) for p in geom.get("fence", [])],
        track,
        accepted,
        geom.get("landing"),
        f"IMAV 2026 Outdoor Mission 1 — {cfg['mission']['name']} — landed {stamp}",
    )
    plan = shared.get("survey_plan")
    summary = {
        "mission": cfg["mission"]["name"],
        "profile": cfg.get("profile"),
        "landed": stamp,
        "mission_start_time": shared.get("mission_start_time"),
        "takeoff_time": shared.get("takeoff_time"),
        "landed_time": landed_time,
        "abort_reason": shared.get("abort_reason"),
        "slot_forced_return": bool(shared.get("slot_forced_return")),
        "plan": plan.summary() if plan is not None else None,
        "vehicles_reported": n,
        "detections_reported": len(detections),
        "detections_accepted": len(accepted),
        "detections_rejected": [
            {
                "reason": d.get("reason"),
                "id": d.get("id"),
                "cls": d.get("cls"),
                "conf": d.get("conf"),
            }
            for d in rejected
        ],
        "detections": accepted,
        "track_points": len(track),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    zpath = run_dir / "results.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in out.iterdir():
            z.write(p, arcname=f"results/{p.name}")
    return {
        "rejected": str(len(rejected)),
        "table": str(out / "mission1_vehicles.csv"),
        "map": str(out / "mission1_map.svg"),
        "summary": str(out / "summary.json"),
        "zip": str(zpath),
        "vehicles": str(n),
    }
