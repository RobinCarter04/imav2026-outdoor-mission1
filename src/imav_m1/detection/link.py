"""File-based link between the mission process and the detection process.

PORTED FROM: SaR sarFlightDay4/cv_comm.py (atomic mode file) — extended with a detections log so
the teammate's detector can be slotted in as a separate process with zero shared code:

  <run_dir>/detections/cv_mode            mission → detector: PASSIVE | DETECTING (atomic replace)
  <run_dir>/telemetry.jsonl               mission → detector: pose stream (mission/telemetry_log.py)
  <run_dir>/detections/detections.jsonl   detector → mission: one JSON object per line:
      {"t": unix_s, "lat": .., "lon": .., "cls": "CCF|VLTT|VT4|GBC180|VBL|unknown",
       "ident": "67-CCF-M-ING" | null, "conf": 0.0-1.0, "image": "relative/path.jpg" | null,
       "id": "any stable id", "source": "yolo|placeholder"}
Full contract: docs/DETECTION_INTERFACE.md. The mission never blocks on the detector; the detector
never sends commands to the aircraft.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

MODES = ("PASSIVE", "DETECTING")


class DetectorLink:
    def __init__(self, run_dir: str | Path):
        self.dir = Path(run_dir) / "detections"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.mode_file = self.dir / "cv_mode"
        self.detections_file = self.dir / "detections.jsonl"

    # ── mission side ──────────────────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"bad detector mode {mode!r}")
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".cv_mode_")
        try:
            os.write(fd, f"{mode}\n".encode())
            os.close(fd)
            os.replace(tmp, self.mode_file)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def read_detections(self) -> list[dict[str, Any]]:
        if not self.detections_file.exists():
            return []
        out = []
        for line in self.detections_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a partially written line — the detector appends atomically per line
        return out

    # ── detector side ─────────────────────────────────────────────────────────────────────────

    def read_mode(self) -> str:
        try:
            return self.mode_file.read_text().strip() or "PASSIVE"
        except FileNotFoundError:
            return "PASSIVE"

    def append_detection(self, det: dict[str, Any]) -> None:
        with open(self.detections_file, "a") as f:
            f.write(json.dumps(det) + "\n")
            f.flush()
