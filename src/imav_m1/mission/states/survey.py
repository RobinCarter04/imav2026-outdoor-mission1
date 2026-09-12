"""SURVEY — PORTED FROM SaR states/search.py phase 2 (AUTO monitor) with the same discipline:

  * drain() first every tick, then read cached mode/telemetry/progress;
  * never fight the pilot or a failsafe: if the mode leaves AUTO we stop commanding. LAND/RTL means
    a failsafe or the pilot is bringing it home → ABORT (no commands). Any other mode = pilot
    override → pause; the mission only continues when the pilot has handed back (GUIDED) AND the
    operator presses RESUME (MissionState.pilot_override_pause); time out → ABORT;
  * completion is judged on MISSION_ITEM_REACHED of the last survey waypoint, not MISSION_CURRENT;
  * the competition slot guard (§2.2) cuts the survey short rather than overrunning: it jumps the
    autopilot to the return leg of the mission already uploaded, so ArduPilot still owns the flying.
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
                    "slot_seconds_left": (
                        None if self.slot_seconds_left() is None else int(self.slot_seconds_left())
                    ),
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
                    nxt = self.pilot_override_pause(mode, override_timeout)
                    if nxt:
                        return nxt
                    continue
            if t.battery_pct is not None and 0 <= t.battery_pct < batt_min:
                return self.go_abort(
                    f"battery {t.battery_pct}% below {batt_min}%", command_rtl=True
                )
            if self.slot_return_due() and not self.shared.get("slot_return_started"):
                nxt = self.next_nav_seq_after(last)
                self.shared["slot_return_started"] = True
                self.shared["slot_forced_return"] = True
                if nxt is None:
                    return self.go_abort(
                        "competition slot guard expired and the mission has no return leg",
                        command_rtl=True,
                    )
                self.log(
                    f"SLOT GUARD: {done_lines}/{total} survey lines done and the slot margin is "
                    f"spent — skipping to the return leg (mission item {nxt})"
                )
                self.vehicle.set_current_mission_item(nxt)
                self.push(
                    "survey",
                    {
                        "status": "RETURNING (slot guard)",
                        "done": done_lines,
                        "total": total,
                        "pct": int(100 * done_lines / total) if total else 0,
                        "elapsed": self.elapsed_str("survey_start_time"),
                        "detections": len(dets),
                    },
                )
                return "RETURN_LAND"
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
