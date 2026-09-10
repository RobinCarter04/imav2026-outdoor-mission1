"""Object detector wrapper.

PORT FROM: SaR robin_package/vision.py (VisionSystem: TFLite / NCNN / Ultralytics backends, lens
undistortion, class filter).
Interface to keep: detect(frame) -> list[Detection(cx, cy, w, h, conf, cls)].
NOTE: Mission 1 targets are vehicles (CCF, VLTT, VT4, GBC 180, VBL; rulebook §5.4.1). The SaR
person model does not apply — see WORKING_NOTES §5 for the identification strategy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    cx: float
    cy: float
    w: float
    h: float
    conf: float
    cls: str


class Detector:
    def __init__(self, cfg: dict):
        self.cfg = cfg["detection"]

    def detect(self, frame) -> list[Detection]:
        raise NotImplementedError("port from SaR vision.py")
