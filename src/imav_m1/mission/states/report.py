"""REPORT — collate and share (rulebook §5.4.1: table + map within 5 min of landing → R = 2).

Writes results/ (vehicle table CSV, map SVG, summary JSON) and results.zip in the run directory,
then publishes paths + the submission countdown to the dashboard. Runs even after ABORT.
"""

from __future__ import annotations

from ...mapping.report import collate
from .common import MissionState


class ReportState(MissionState):
    name = "REPORT"

    def execute(self) -> str:
        self.detector_mode("PASSIVE")
        landed = self.shared.get("landed_time") or self.now()
        deadline_s = float(self.cfg.get("deliverables", {}).get("submit_deadline_s", 300))
        try:
            dets = self.detections()
            track = self.ctx.telemetry_log.track() if self.ctx.telemetry_log is not None else []
            paths = collate(
                self.ctx.run_dir, self.cfg, self.shared, dets, track, landed_time=landed
            )
        except Exception as e:  # noqa: BLE001 — a report failure must never strand the machine
            self.log(f"ERROR building results: {e}")
            paths = {"error": str(e)}
        self.shared["results"] = {
            "paths": paths,
            "landed_time": landed,
            "deadline": landed + deadline_s,
        }
        self.push("results", {**self.shared["results"], "detections": len(self.detections())})
        self.log(f"Results ready: {paths}")
        return "DONE"
