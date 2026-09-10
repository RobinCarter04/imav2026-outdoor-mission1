"""Helpers shared by states (mixed into BaseState behaviour without cross-imports)."""

from __future__ import annotations

from typing import Any

from ..framework import BaseState

MISSION_KEYS_PREFIXES = (
    "survey_",
    "mission_",
    "takeoff_",
    "abort_",
    "landed_",
    "results",
    "fence_uploaded",
    "mission_uploaded",
    "mission_items",
    "survey_plan",
    "survey_seq_range",
    "plan_geometry",
)


class MissionState(BaseState):
    """BaseState + the conveniences the ported SaR states relied on."""

    def return_next(self, default: str = "IDLE") -> str:
        """SaR `return_to` semantics, plus a return stack for chained subroutines."""
        if "return_to" in self.shared:
            return self.shared.pop("return_to")
        stack = self.shared.get("return_stack")
        if stack:
            return stack.pop()
        return default

    def tick(self) -> float:
        return float(self.cfg.get("operator", {}).get("tick_s", 0.5))

    def telemetry_snapshot(self) -> dict[str, Any]:
        t = self.vehicle.telemetry()
        return {
            "mode": self.vehicle.mode(),
            "armed": self.vehicle.armed(),
            "lat": round(t.lat, 7) if t.lat is not None else None,
            "lon": round(t.lon, 7) if t.lon is not None else None,
            "alt": round(t.alt_rel_m, 1) if t.alt_rel_m is not None else None,
            "heading": t.heading_deg,
            "groundspeed": t.groundspeed_mps,
            "sats": t.satellites,
            "gps_fix": t.gps_fix,
            "battery_pct": t.battery_pct,
            "battery_v": t.battery_v,
        }

    def record_telemetry(self, **extra: Any) -> None:
        if self.ctx.telemetry_log is not None:
            cur, reached = self.vehicle.mission_progress()
            self.ctx.telemetry_log.record(
                self.vehicle.telemetry(),
                self.vehicle.mode(),
                self.vehicle.armed(),
                self.name,
                cur,
                reached,
                self.now(),
                **extra,
            )

    def push_telemetry(self) -> None:
        self.push("telemetry", self.telemetry_snapshot())

    def detector_mode(self, mode: str) -> None:
        if self.ctx.detector is not None:
            self.ctx.detector.set_mode(mode)

    def detections(self) -> list[dict[str, Any]]:
        return self.ctx.detector.read_detections() if self.ctx.detector is not None else []

    def is_abort_command(self, cmd: dict[str, Any] | None) -> bool:
        return bool(cmd) and cmd.get("type") == "abort"

    def go_abort(self, reason: str, command_rtl: bool) -> str:
        self.shared["abort_reason"] = reason
        self.shared["abort_command_rtl"] = command_rtl
        self.log(f"ABORT: {reason}")
        return "ABORT"

    def elapsed_str(self, key: str = "mission_start_time") -> str:
        start = self.shared.get(key)
        if start is None:
            return "0:00"
        e = int(self.now() - start)
        return f"{e // 60}:{e % 60:02d}"

    def clear_mission_keys(self) -> None:
        for k in list(self.shared.keys()):
            if k.startswith(MISSION_KEYS_PREFIXES):
                del self.shared[k]
