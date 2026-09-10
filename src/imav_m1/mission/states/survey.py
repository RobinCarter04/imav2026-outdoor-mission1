"""SURVEY — PORTED FROM SaR states/search.py phase 2 (AUTO monitor) with the same discipline:

  * drain() first every tick, then read cached mode/telemetry/progress;
  * never fight the pilot or a failsafe: if the mode leaves AUTO we stop commanding. LAND/RTL means
    a failsafe or the pilot is bringing it home → ABORT (no commands). Any other mode = pilot
    override → wait for a GUIDED hand-back, then re-request AUTO; time out → ABORT;
  * completion is judged on MISSION_ITEM_REACHED of the last survey waypoint, not MISSION_CURRENT.
The detector is told DETECTING for the duration; detections are surfaced to the dashboard.
"""

from __future__ import annotations

from .common import MissionState


class SurveyState(MissionState):
    name = "SURVEY"

    def enter(self) -> None:
        first, last = self.shared.get("survey_seq_range", (None, None))
        self.log(f"SURVEY — monitoring AUTO mission items {first}..{last}")
        self.detector_mode("DETECTING")
        self.shared.setdefault("survey_start_time", self.now())
        self.shared.setdefault("survey_last_reached", -1)
        self._unknown_streak = 0

    def exit(self) -> None:
        self.detector_mode("PASSIVE")

    def execute(self) -> str:
        first, last = self.shared["survey_seq_range"]
        total = last - first + 1
        ops = self.cfg.get("operator", {})
        override_timeout = float(ops.get("override_timeout_s", 120))
        batt_min = int(self.cfg["safety"].get("battery_failsafe_pct", 25))

        while True:
            self.vehicle.drain()
            mode = self.vehicle.mode()
            t = self.vehicle.telemetry()
            cur, reached = self.vehicle.mission_progress()
            if reached is not None and reached > self.shared["survey_last_reached"]:
                self.shared["survey_last_reached"] = reached
                if first <= reached <= last:
                    self.log(f"survey waypoint {reached - first + 1}/{total} reached")
            self.record_telemetry()
            done_lines = max(0, min(total, self.shared["survey_last_reached"] - first + 1))
            dets = self.detections()
            self.push(
                "survey",
                {
                    "status": "FLYING",
                    "current_seq": cur,
                    "reached_seq": self.shared["survey_last_reached"],
                    "done": done_lines,
                    "total": total,
                    "pct": int(100 * done_lines / total) if total else 0,
                    "elapsed": self.elapsed_str("survey_start_time"),
                    "detections": len(dets),
                },
            )
            self.push("detections", dets[-50:])
            self.push_telemetry()

            # ── mode discipline ───────────────────────────────────────────────────────────────
            if mode == "UNKNOWN":
                self._unknown_streak += 1
                if self._unknown_streak >= int(ops.get("heartbeat_miss_limit", 10)):
                    return self.go_abort("lost autopilot heartbeat", command_rtl=False)
            else:
                self._unknown_streak = 0
                if mode in ("RTL", "LAND", "SMART_RTL"):
                    return self.go_abort(
                        f"autopilot/pilot switched to {mode} (failsafe?)", command_rtl=False
                    )
                if mode != "AUTO":
                    nxt = self._pilot_override(mode, override_timeout)
                    if nxt:
                        return nxt
                    continue
            if t.battery_pct is not None and 0 <= t.battery_pct < batt_min:
                return self.go_abort(
                    f"battery {t.battery_pct}% below {batt_min}%", command_rtl=True
                )
            if self.is_abort_command(self.consume_command()):
                return self.go_abort("operator abort", command_rtl=True)
            if self.shared["survey_last_reached"] >= last:
                self.log("SURVEY COMPLETE — last survey waypoint reached")
                self.push(
                    "survey",
                    {
                        "status": "COMPLETE",
                        "done": total,
                        "total": total,
                        "pct": 100,
                        "elapsed": self.elapsed_str("survey_start_time"),
                        "detections": len(dets),
                    },
                )
                return "RETURN_LAND"
            self.sleep(self.tick())

    def _pilot_override(self, mode: str, timeout: float) -> str | None:
        """Pilot took the sticks. Wait for GUIDED hand-back (SaR convention), then resume AUTO."""
        self.log(f"PILOT OVERRIDE (mode={mode}) — survey paused, not commanding")
        self.push("survey", {"status": f"PAUSED (pilot: {mode})"})
        start = self.now()
        while self.now() - start < timeout:
            self.sleep(self.tick())
            self.vehicle.drain()
            self.record_telemetry()
            self.push_telemetry()
            m = self.vehicle.mode()
            if m == "GUIDED":
                self.log("pilot handed back (GUIDED) — re-requesting AUTO")
                if self.vehicle.set_mode("AUTO"):
                    return None  # resume monitoring
                return self.go_abort("AUTO refused after hand-back", command_rtl=False)
            if m in ("RTL", "LAND"):
                return self.go_abort(f"pilot chose {m}", command_rtl=False)
            if self.is_abort_command(self.consume_command()):
                return self.go_abort("operator abort during override", command_rtl=False)
        return self.go_abort("pilot override timeout", command_rtl=False)
