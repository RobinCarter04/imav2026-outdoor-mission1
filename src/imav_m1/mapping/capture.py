"""Pose-tagged image capture for the mapping deliverable (E-02).

Writes images to <run>/images/ with a sidecar CSV (filename, lat, lon, alt, yaw, roll, pitch, t).
Capture interval derived from front overlap, speed and footprint (mission.survey.overlap_front).
The map/orthomosaic itself is produced by tools/ after landing unless the rulebook requires it live
(open question in WORKING_NOTES.md §5).
"""

from __future__ import annotations


class PoseTaggedCapture:
    def __init__(self, cfg: dict, out_dir: str):
        self.cfg = cfg
        self.out_dir = out_dir

    def maybe_capture(self, frame, pose) -> bool:
        raise NotImplementedError
