"""Helpers shared by states (mixed into BaseState behaviour without cross-imports)."""

from __future__ import annotations

from typing import Any

from ..framework import BaseState

# The pilot signals "you may have it back" by putting the mode switch here. The mission still does
# not move until the OPERATOR presses RESUME (docs/SAFETY.md).
RESUMABLE_MODES = ("GUIDED", "AUTO")
# Modes that mean the pilot or a failsafe is bringing the aircraft home — never resume from these.
PILOT_RECOVERY_MODES = ("RTL", "LAND", "SMART_RTL", "AUTO_RTL", "BRAKE")

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

    def pilot_override_pause(self, mode: str, timeout_s: float) -> str | None:
        """The safety pilot has control. Command NOTHING and wait.

        Two independent gates must both be satisfied before the mission flies again:
          1. the PILOT hands back, by putting the aircraft in GUIDED (or AUTO);
          2. the OPERATOR presses RESUME in the dashboard.
        A RESUME arriving while the pilot still holds it (LOITER, STABILIZE, POSHOLD, ...) is
        rejected and not remembered — the operator presses it again after the hand-back.

        Returns None to resume the caller's monitoring loop, or the name of the next state.
        """
        self.log(
            f"PILOT OVERRIDE (mode={mode}) — paused, sending nothing. "
            f"Pilot: return to GUIDED to hand back. Operator: then press RESUME."
        )
        start = self.now()
        while self.now() - start < timeout_s:
            self.sleep(self.tick())
            self.vehicle.drain()
            self.record_telemetry()
            self.push_telemetry()
            m = self.vehicle.mode()

            if self.vehicle.armed() is False:
                self.shared["landed_time"] = self.now()
                self.log("aircraft disarmed while the pilot had control — going to REPORT")
                self.push("override", None)
                return "REPORT"
            if m in PILOT_RECOVERY_MODES:
                self.push("override", None)
                return self.go_abort(f"pilot/failsafe chose {m}", command_rtl=False)

            can_resume = m in RESUMABLE_MODES
            self.push(
                "override",
                {
                    "paused": True,
                    "mode": m,
                    "can_resume": can_resume,
                    "waiting_for": "operator RESUME" if can_resume else "pilot to return to GUIDED",
                    "seconds_left": int(timeout_s - (self.now() - start)),
                },
            )

            cmd = self.consume_command()
            if cmd:
                kind = cmd.get("type")
                if kind == "abort":
                    self.push("override", None)
                    return self.go_abort("operator abort during override", command_rtl=False)
                if kind == "resume":
                    if not can_resume:
                        self.log(
                            f"RESUME REJECTED — aircraft is in {m}; the pilot must return it to "
                            f"GUIDED before the mission can continue"
                        )
                    elif m == "AUTO":
                        self.log("operator RESUME — already in AUTO, resuming monitoring")
                        self.push("override", None)
                        return None
                    elif self.vehicle.set_mode("AUTO"):
                        self.log("operator RESUME — AUTO confirmed, continuing")
                        self.push("override", None)
                        return None
                    else:
                        self.push("override", None)
                        return self.go_abort(
                            "AUTO refused after operator RESUME", command_rtl=False
                        )

        self.push("override", None)
        return self.go_abort(
            f"pilot override timeout ({timeout_s:.0f} s with no operator RESUME)", command_rtl=False
        )

    # ── competition slot guard (§2.2) ─────────────────────────────────────────────────────
    def slot_return_deadline_s(self) -> float | None:
        """Wall-clock time by which the return leg must start, or None when the guard is off."""
        m = self.cfg["mission"]
        duration, margin = m.get("slot_duration_s"), m.get("return_margin_s")
        start = self.shared.get("mission_start_time")
        if not duration or start is None:
            return None
        return float(start) + float(duration) - float(margin or 0.0)

    def slot_seconds_left(self) -> float | None:
        deadline = self.slot_return_deadline_s()
        return None if deadline is None else deadline - self.now()

    def slot_return_due(self) -> bool:
        left = self.slot_seconds_left()
        return left is not None and left <= 0.0

    def next_nav_seq_after(self, seq: int) -> int | None:
        """First navigation item after `seq` — where the return leg starts."""
        for item in self.shared.get("mission_items", []):
            if item.seq > seq and item.is_nav:
                return item.seq
        return None

    def clear_mission_keys(self) -> None:
        for k in list(self.shared.keys()):
            if k.startswith(MISSION_KEYS_PREFIXES):
                del self.shared[k]
