"""Tick-driven in-memory Vehicle for unit tests. Deterministic, no I/O, no threads, no wall clock.

`advance(dt)` moves the simulated aircraft: climbs on takeoff, flies AUTO missions waypoint by
waypoint at `speed_mps`, lands on NAV_LAND / LAND / RTL and disarms on the ground. Enough fidelity
for the state machine, survey monitoring, telemetry logging and the placeholder detector.
Test helpers: `pilot_set_mode()` (RC override), `fail_next_upload`, `reject_modes`.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..mission import geo
from .interface import (
    MAV_CMD_NAV_LAND,
    MAV_CMD_NAV_TAKEOFF,
    MAV_CMD_NAV_WAYPOINT,
    FencePolygon,
    MissionItem,
    Telemetry,
)


class FakeVehicle:
    def __init__(
        self,
        home: tuple[float, float] = (48.806567, 7.852134),
        speed_mps: float = 10.0,
        climb_mps: float = 2.5,
        descent_mps: float = 1.5,
        battery_pct: int = 100,
    ):
        self.home = home
        self.speed = speed_mps
        self.climb = climb_mps
        self.descent = descent_mps
        self._mode = "STABILIZE"
        self._armed = False
        self._connected = False
        self.lat, self.lon, self.alt = home[0], home[1], 0.0
        self.heading = 0.0
        self.t = 0.0
        self.battery = battery_pct
        self.satellites, self.gps_fix = 12, 3
        self.params: dict[str, float] = {}
        self.mission: list[MissionItem] = []
        self.fences: list[FencePolygon] = []
        self._current: int | None = None
        self._reached: int | None = None
        self._takeoff_target: float | None = None
        self.calls: list[str] = []
        self.reject_modes: set[str] = set()
        self.fail_next_upload = False
        self.log_lines: list[str] = []

    # ── Vehicle protocol ──────────────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._connected = True
        self.calls.append("connect")

    def close(self) -> None:
        self._connected = False
        self.calls.append("close")

    def drain(self) -> None:
        pass

    def mode(self) -> str:
        return self._mode if self._connected else "UNKNOWN"

    def set_mode(self, mode: str) -> bool:
        self.calls.append(f"mode:{mode}")
        if mode in self.reject_modes:
            return False
        self._mode = mode
        if mode == "AUTO" and self.mission and self._current in (None, 0):
            self._start_mission()  # resume otherwise, like ArduPilot with MIS_RESTART=0
        return True

    def armed(self) -> bool | None:
        return self._armed if self._connected else None

    def arm(self, timeout_s: float) -> bool:
        self.calls.append("arm")
        if self.gps_fix < 3:
            return False
        self._armed = True
        return True

    def takeoff(self, alt_m: float) -> None:
        self.calls.append(f"takeoff:{alt_m}")
        if self._armed and self._mode == "GUIDED":
            self._takeoff_target = float(alt_m)

    def telemetry(self) -> Telemetry:
        return Telemetry(
            lat=self.lat,
            lon=self.lon,
            alt_rel_m=self.alt,
            alt_msl_m=self.alt + 150.0,
            heading_deg=self.heading,
            groundspeed_mps=self.speed if self._flying() else 0.0,
            satellites=self.satellites,
            gps_fix=self.gps_fix,
            battery_v=22.2,
            battery_pct=self.battery,
            ekf_flags=0x1FF,
            timestamp_s=self.t,
        )

    def upload_mission(self, items: Sequence[MissionItem]) -> bool:
        self.calls.append(f"upload_mission:{len(items)}")
        if self.fail_next_upload:
            self.fail_next_upload = False
            return False
        self.mission = list(items)
        self._current, self._reached = 0, None
        return True

    def upload_fence(self, polygons: Sequence[FencePolygon]) -> bool:
        self.calls.append(f"upload_fence:{len(polygons)}")
        self.fences = list(polygons)
        return True

    def mission_count(self) -> int:
        return len(self.mission)

    def fence_count(self) -> int:
        return sum(len(p.points) for p in self.fences)

    def mission_progress(self) -> tuple[int | None, int | None]:
        return self._current, self._reached

    def set_current_mission_item(self, seq: int) -> None:
        self._current = seq

    def clear_mission_progress_cache(self) -> None:
        self._current, self._reached = None, None

    def set_param(self, name: str, value: float, wait: bool = False) -> bool:
        self.params[name] = float(value)
        return True

    def set_speed(self, mps: float) -> None:
        self.calls.append(f"speed:{mps}")
        self.speed = float(mps)

    def log(self, tag: str, message: str) -> None:
        self.log_lines.append(f"[{tag}] {message}")

    # ── test helpers ──────────────────────────────────────────────────────────────────────────

    def pilot_set_mode(self, mode: str) -> None:
        """Simulate the safety pilot flipping the RC mode switch."""
        self._mode = mode

    def _flying(self) -> bool:
        return self._armed and self.alt > 0.05

    def _start_mission(self) -> None:
        self._current = self._next_nav_seq(0)

    def _next_nav_seq(self, after: int) -> int | None:
        for it in self.mission:
            if it.seq > after and it.is_nav:
                return it.seq
        return None

    def advance(self, dt: float = 1.0) -> None:
        """Advance simulated time by dt seconds."""
        self.t += dt
        if not self._armed:
            return
        # takeoff (GUIDED)
        if self._takeoff_target is not None and self._mode == "GUIDED":
            self.alt = min(self._takeoff_target, self.alt + self.climb * dt)
            return
        if self._mode in ("LAND", "RTL"):
            if self._mode == "RTL":
                self._move_towards(self.home, dt)
                if geo.distance_m((self.lat, self.lon), self.home) > 1.0:
                    return
            self.alt = max(0.0, self.alt - self.descent * dt)
            if self.alt <= 0.0:
                self._armed = False
            return
        if self._mode == "AUTO" and self._current is not None and self.mission:
            item = self.mission[self._current]
            if item.command == MAV_CMD_NAV_WAYPOINT:
                if self.alt < item.alt - 0.5:
                    self.alt = min(item.alt, self.alt + self.climb * dt)
                arrived = self._move_towards((item.lat, item.lon), dt)
                if arrived:
                    self._reached = item.seq
                    nxt = self._next_nav_seq(item.seq)
                    if nxt is not None:
                        self._current = nxt
            elif item.command == MAV_CMD_NAV_LAND:
                if item.lat or item.lon:
                    if not self._move_towards((item.lat, item.lon), dt):
                        return
                self.alt = max(0.0, self.alt - self.descent * dt)
                if self.alt <= 0.0:
                    self._reached = item.seq
                    self._armed = False
            elif item.command == MAV_CMD_NAV_TAKEOFF:
                self.alt = min(item.alt, self.alt + self.climb * dt)
                if self.alt >= item.alt - 0.1:
                    self._reached = item.seq
                    self._current = self._next_nav_seq(item.seq)

    def _move_towards(self, target: tuple[float, float], dt: float) -> bool:
        d = geo.distance_m((self.lat, self.lon), target)
        step = self.speed * dt
        if d <= step or d < 0.5:
            self.lat, self.lon = target
            return True
        self.heading = geo.bearing_deg((self.lat, self.lon), target)
        frac = step / d
        self.lat += (target[0] - self.lat) * frac
        self.lon += (target[1] - self.lon) * frac
        return False
