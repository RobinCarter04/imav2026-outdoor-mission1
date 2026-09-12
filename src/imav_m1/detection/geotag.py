"""Turn per-frame bounding boxes into the vehicle rows we submit.

This is the whole geotagging chain in one place, and it runs the same way in the air or afterwards
on a laptop:

    raw_detections.jsonl  (detector: boxes in pixels, with a frame timestamp)
  + telemetry.jsonl       (mission: pose stream)
  -> georef.pixel_to_latlon   one ground fix per box
  -> aggregate.VehicleAggregator   one row per vehicle
  -> detections.jsonl     (docs/DETECTION_INTERFACE.md), then detection/filter.py decides

Because it needs nothing but two files, a recorded sortie can be re-processed as many times as you
like: retune, recalibrate, re-run. The detector never has to know the aircraft exists.

    python -m imav_m1.detection.geotag --run-dir data/flights/latest
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .aggregate import UNKNOWN, Observation, VehicleAggregator
from .georef import Camera, Pose, PoseBuffer, off_nadir_fraction, pixel_to_latlon

RAW_NAME = "raw_detections.jsonl"


def georef_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    out = {"terrain_offset_m": 0.0, "max_pose_gap_s": 0.5}
    out.update((cfg.get("detection") or {}).get("georef") or {})
    return out


def load_poses(telemetry_path: str | Path, max_gap_s: float = 0.5) -> PoseBuffer:
    """Read <run_dir>/telemetry.jsonl into a buffer. Lines without a fix are skipped."""
    buf = PoseBuffer(max_gap_s=max_gap_s)
    for line in _lines(telemetry_path):
        if line.get("lat") is None or line.get("lon") is None or line.get("alt") is None:
            continue
        buf.add(
            Pose(
                lat=float(line["lat"]),
                lon=float(line["lon"]),
                alt_m=float(line["alt"]),
                yaw_deg=float(line.get("hdg") or 0.0),
                pitch_deg=float(line.get("pitch") or 0.0),
                roll_deg=float(line.get("roll") or 0.0),
                t=float(line["t"]),
            )
        )
    return buf


def pixel_of(row: dict[str, Any], cam: Camera) -> tuple[float, float] | None:
    """Centre of the reported box, scaled to the camera's own resolution.

    Accepts either ``px``/``py`` or ``bbox: [x1, y1, x2, y2]``. A detector that runs on a resized
    frame should say so with ``frame_w``/``frame_h``; without them the box is assumed to be in full
    camera pixels.
    """
    if row.get("px") is not None and row.get("py") is not None:
        px, py = float(row["px"]), float(row["py"])
    elif row.get("bbox"):
        x1, y1, x2, y2 = (float(v) for v in row["bbox"])
        px, py = (x1 + x2) / 2.0, (y1 + y2) / 2.0  # nadir camera: the centre, not the bottom edge
    else:
        return None
    fw, fh = float(row.get("frame_w") or cam.width), float(row.get("frame_h") or cam.height)
    if fw <= 0 or fh <= 0:
        return None
    return px * cam.width / fw, py * cam.height / fh


def observations(
    raw_rows: list[dict[str, Any]], poses: PoseBuffer, cam: Camera, cfg: dict[str, Any]
) -> tuple[list[Observation], list[dict[str, Any]]]:
    """Project every box. Returns (observations, skipped), each skipped row carrying a reason."""
    gs = georef_settings(cfg)
    terrain = float(gs["terrain_offset_m"])
    mount = float((cfg.get("camera") or {}).get("mount_yaw_offset_deg") or 0.0)

    out: list[Observation] = []
    skipped: list[dict[str, Any]] = []

    for row in raw_rows:
        t = row.get("t")
        if t is None:
            skipped.append({**row, "reason": "no frame timestamp"})
            continue
        pixel = pixel_of(row, cam)
        if pixel is None:
            skipped.append({**row, "reason": "no px/py and no bbox"})
            continue
        pose = poses.at(float(t))
        if pose is None:
            skipped.append({**row, "reason": "no telemetry within the pose gap"})
            continue
        pose = Pose(
            lat=pose.lat,
            lon=pose.lon,
            alt_m=pose.alt_m + terrain,
            yaw_deg=pose.yaw_deg,
            pitch_deg=pose.pitch_deg,
            roll_deg=pose.roll_deg,
            t=pose.t,
        )
        fix = pixel_to_latlon(pixel[0], pixel[1], pose, cam, mount_yaw_offset_deg=mount)
        if fix is None:
            skipped.append({**row, "reason": "ray did not reach the ground (attitude too large)"})
            continue
        out.append(
            Observation(
                lat=fix[0],
                lon=fix[1],
                cls=str(row.get("cls") or UNKNOWN),
                conf=float(row.get("conf") or 0.0),
                t=float(t),
                quality=1.0 - off_nadir_fraction(pixel[0], pixel[1], cam),
                image=row.get("image"),
            )
        )
    return out, skipped


def run(run_dir: str | Path, cfg: dict[str, Any], write: bool = True) -> dict[str, Any]:
    """Geotag a run directory. Writes detections/detections.jsonl unless write=False."""
    run_dir = Path(run_dir)
    cam = Camera.from_config(cfg)
    gs = georef_settings(cfg)
    poses = load_poses(run_dir / "telemetry.jsonl", float(gs["max_pose_gap_s"]))
    raw = list(_lines(run_dir / "detections" / RAW_NAME))

    obs, skipped = observations(raw, poses, cam, cfg)
    agg = VehicleAggregator(cfg)
    agg.add_many(obs)
    vehicles, dropped = agg.vehicles(), agg.dropped()

    if write:
        out = run_dir / "detections" / "detections.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            for v in vehicles:
                f.write(json.dumps(v) + "\n")

    return {
        "poses": len(poses),
        "boxes": len(raw),
        "projected": len(obs),
        "skipped": len(skipped),
        "skipped_rows": skipped,
        "vehicles": vehicles,
        "dropped": dropped,
    }


def _lines(path: str | Path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def main(argv: list[str] | None = None) -> int:
    from ..config.loader import load_config

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--profile", default="sim")
    ap.add_argument("--site", default=None)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    a = ap.parse_args(argv)

    cfg = load_config(a.profile, a.site)
    r = run(a.run_dir, cfg, write=not a.dry_run)
    print(
        f"{r['poses']} poses, {r['boxes']} boxes, {r['projected']} projected, "
        f"{r['skipped']} skipped -> {len(r['vehicles'])} vehicles "
        f"({len(r['dropped'])} too thin to report)"
    )
    for v in r["vehicles"]:
        print(
            f"  {v['id']}  {v['cls']:8s}  {v['lat']:.7f}, {v['lon']:.7f}  "
            f"±{v['position_error_m']:.1f} m  from {v['n_obs']} frames"
        )
    for s in r["skipped_rows"][:10]:
        print(f"  skipped: {s['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
