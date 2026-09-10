"""PREFLIGHT_CHECK — PORTED FROM SaR states/pre_auto_check.py, re-based for a ground start.

Automated checks (cfg.preflight thresholds) + one operator checkbox (safety pilot ready). The
operator's START is the single manual action of the mission (E-09): it is only accepted when every
check is green. `start_mission` with when_ready=true (headless / --auto runs) arms the start to fire
as soon as the checks pass, within auto_start_timeout_s.
"""

from __future__ import annotations

from typing import Any

from .common import MissionState

EKF_HEALTHY_MASK = (
    0x01 | 0x02 | 0x10 | 0x20
)  # attitude, velocity_horiz, pos_horiz_abs, pos_vert_abs


class PreflightCheckState(MissionState):
    name = "PREFLIGHT_CHECK"

    def enter(self) -> None:
        self.log("PREFLIGHT_CHECK — waiting for all checks green + operator START")
        self.shared.setdefault("pilot_ready", False)
        self._auto_start_at: float | None = None
        self._counts_at = 0.0

    def execute(self) -> str:
        pf = self.cfg.get("preflight", {})
        while True:
            self.vehicle.drain()
            checks = self._evaluate(pf)
            self.push("preflight", checks)
            self.push_telemetry()

            cmd = self.consume_command()
            if cmd:
                kind = cmd.get("type")
                if kind == "pilot_ready":
                    self.shared["pilot_ready"] = bool(
                        cmd.get("value", not self.shared["pilot_ready"])
                    )
                    self.log(f"pilot ready = {self.shared['pilot_ready']}")
                elif kind == "start_mission":
                    if checks["all_ready"]:
                        return self._start()
                    if cmd.get("when_ready"):
                        self._auto_start_at = self.now() + float(
                            pf.get("auto_start_timeout_s", 180)
                        )
                        self.log("start armed — will take off as soon as all checks pass")
                    else:
                        self.log(
                            "START rejected — not all checks green: " + ", ".join(checks["failing"])
                        )
                elif kind in ("cancel", "abort"):
                    self.log("cancelled — returning to IDLE")
                    return "IDLE"
            if self._auto_start_at is not None:
                if checks["all_ready"]:
                    return self._start()
                if self.now() > self._auto_start_at:
                    self.shared["last_error"] = "auto start timed out: " + ", ".join(
                        checks["failing"]
                    )
                    self.log(self.shared["last_error"])
                    return "IDLE"
            self.sleep(self.tick())

    def _start(self) -> str:
        self.log("START approved — all checks green")
        self.shared["mission_start_time"] = self.now()
        return "TAKEOFF"

    def _evaluate(self, pf: dict[str, Any]) -> dict[str, Any]:
        t = self.vehicle.telemetry()
        mode = self.vehicle.mode()
        armed = self.vehicle.armed()
        if self.now() - self._counts_at > float(pf.get("count_query_interval_s", 15)):
            self.shared["_mission_count"] = self.vehicle.mission_count()
            self.shared["_fence_count"] = self.vehicle.fence_count()
            self._counts_at = self.now()
        expected_items = len(self.shared.get("mission_items", []))
        area = self.shared.get("area")
        ekf = t.ekf_flags
        checks = {
            "heartbeat": (mode != "UNKNOWN", mode),
            "gps": (
                (t.gps_fix or 0) >= int(pf.get("min_gps_fix", 3))
                and (t.satellites or 0) >= int(pf.get("min_satellites", 8)),
                f"fix={t.gps_fix} sats={t.satellites}",
            ),
            "ekf": (
                ekf is not None and (ekf & EKF_HEALTHY_MASK) == EKF_HEALTHY_MASK,
                f"flags={ekf}",
            ),
            "battery": (
                t.battery_pct is not None and t.battery_pct >= int(pf.get("min_battery_pct", 40)),
                f"{t.battery_pct}%",
            ),
            "disarmed": (armed is False, "armed" if armed else "disarmed"),
            "mission": (
                self.shared.get("_mission_count", 0) == expected_items and expected_items > 0,
                f"{self.shared.get('_mission_count', 0)}/{expected_items} items",
            ),
            "fence": (
                self.shared.get("_fence_count", 0) >= 3 and bool(self.shared.get("fence_uploaded")),
                f"{self.shared.get('_fence_count', 0)} vertices",
            ),
            "area": (area is not None and len(area.survey) >= 3, area.source if area else "none"),
            "pilot_ready": (bool(self.shared.get("pilot_ready")), "operator checkbox"),
        }
        out = {k: {"pass": bool(v[0]), "detail": str(v[1])} for k, v in checks.items()}
        out["failing"] = [k for k, v in checks.items() if not v[0]]
        out["all_ready"] = not out["failing"]
        out["auto_start_armed"] = self._auto_start_at is not None
        return out
