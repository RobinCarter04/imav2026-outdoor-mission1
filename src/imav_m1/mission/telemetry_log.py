"""Append-only pose/telemetry stream for the run: <run_dir>/telemetry.jsonl.

Consumers: the detector process (geotagging), REPORT (flown track for the map), post-flight tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..vehicle.interface import Telemetry


class TelemetryLog:
    def __init__(self, run_dir: str | Path, min_interval_s: float = 0.25):
        self.path = Path(run_dir) / "telemetry.jsonl"
        self.min_interval_s = min_interval_s
        self._last_t = -1e9
        self._f = open(self.path, "a")  # noqa: SIM115 — long-lived handle, closed in close()

    def record(
        self,
        t: Telemetry,
        mode: str,
        armed: bool | None,
        state: str,
        cur_seq,
        reached_seq,
        now: float,
        **extra: Any,
    ) -> None:
        if now - self._last_t < self.min_interval_s:
            return
        self._last_t = now
        row = {
            "t": round(now, 3),
            "state": state,
            "mode": mode,
            "armed": armed,
            "lat": t.lat,
            "lon": t.lon,
            "alt": t.alt_rel_m,
            "hdg": t.heading_deg,
            "gs": t.groundspeed_mps,
            "sats": t.satellites,
            "fix": t.gps_fix,
            "batt": t.battery_pct,
            "wp": cur_seq,
            "reached": reached_seq,
        }
        row.update(extra)
        self._f.write(json.dumps(row) + "\n")
        self._f.flush()

    def track(
        self, states: tuple[str, ...] = ("TAKEOFF", "SURVEY", "RETURN_LAND", "ABORT")
    ) -> list[tuple[float, float]]:
        self._f.flush()
        out = []
        for line in self.path.read_text().splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("lat") is not None and d.get("state") in states:
                out.append((d["lat"], d["lon"]))
        return out

    def close(self) -> None:
        self._f.close()
