"""Vehicle abstraction (ADR-003). Mission code depends on this, never on pymavlink directly.

The surface mirrors what the SaR states actually used from `DroneConnection` (drain / mode / arm /
telemetry / mission + fence upload / params / progress) so the ported states read the same way.
MAVLink numeric constants are repeated here so callers never import pymavlink.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

# ── MAVLink constants (copied, so this module has no pymavlink dependency) ───────────────────
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_DO_CHANGE_SPEED = 178
MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION = 5001
MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION = 5002
MAV_FRAME_GLOBAL = 0
MAV_FRAME_MISSION = 2
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
NAV_COMMANDS = {MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_LAND, MAV_CMD_NAV_TAKEOFF}

# ArduCopter flight-mode numbers (from SaR config.py, extended)
COPTER_MODES = {
    "STABILIZE": 0,
    "ACRO": 1,
    "ALT_HOLD": 2,
    "AUTO": 3,
    "GUIDED": 4,
    "LOITER": 5,
    "RTL": 6,
    "CIRCLE": 7,
    "LAND": 9,
    "DRIFT": 11,
    "SPORT": 13,
    "FLIP": 14,
    "AUTOTUNE": 15,
    "POSHOLD": 16,
    "BRAKE": 17,
    "THROW": 18,
    "AVOID_ADSB": 19,
    "GUIDED_NOGPS": 20,
    "SMART_RTL": 21,
    "FLOWHOLD": 22,
    "FOLLOW": 23,
    "ZIGZAG": 24,
    "SYSTEMID": 25,
    "AUTOROTATE": 26,
    "AUTO_RTL": 27,
}
COPTER_MODE_NAMES = {v: k for k, v in COPTER_MODES.items()}


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    alt_m: float  # relative to home


@dataclass(frozen=True)
class MissionItem:
    """One MISSION_ITEM_INT. Build with the helpers in mission/items.py."""

    seq: int
    command: int
    frame: int = MAV_FRAME_GLOBAL_RELATIVE_ALT
    p1: float = 0.0
    p2: float = 0.0
    p3: float = 0.0
    p4: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0

    @property
    def is_nav(self) -> bool:
        return self.command in NAV_COMMANDS


@dataclass(frozen=True)
class FencePolygon:
    kind: str  # "inclusion" | "exclusion"
    points: tuple[tuple[float, float], ...]
    label: str = ""


@dataclass
class Telemetry:
    lat: float | None = None
    lon: float | None = None
    alt_rel_m: float | None = None  # relative to home (GLOBAL_POSITION_INT)
    alt_msl_m: float | None = None
    heading_deg: float | None = None
    pitch_deg: float | None = None  # ATTITUDE; georeferencing needs it (detection/georef.py)
    roll_deg: float | None = None
    groundspeed_mps: float | None = None
    satellites: int | None = None
    gps_fix: int | None = None
    battery_v: float | None = None
    battery_pct: int | None = None  # -1 / None if unknown
    ekf_flags: int | None = None
    timestamp_s: float = 0.0
    extra: dict = field(default_factory=dict)

    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None


class Vehicle(Protocol):
    """Call `drain()` at the top of every loop tick, then read cached state (SaR buffer pattern)."""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def drain(self) -> None: ...
    def mode(self) -> str: ...  # "UNKNOWN" until an autopilot heartbeat is cached
    def set_mode(self, mode: str) -> bool: ...  # blocks up to the configured timeout, confirms
    def armed(self) -> bool | None: ...
    def arm(self, timeout_s: float) -> bool: ...
    def takeoff(self, alt_m: float) -> None: ...  # GUIDED NAV_TAKEOFF; caller polls altitude
    def telemetry(self) -> Telemetry: ...
    def upload_mission(self, items: Sequence[MissionItem]) -> bool: ...
    def upload_fence(self, polygons: Sequence[FencePolygon]) -> bool: ...
    def mission_count(self) -> int: ...
    def fence_count(self) -> int: ...
    def mission_progress(
        self,
    ) -> tuple[int | None, int | None]: ...  # (current seq, last reached seq)
    def set_current_mission_item(self, seq: int) -> None: ...
    def clear_mission_progress_cache(self) -> None: ...
    def set_param(self, name: str, value: float, wait: bool = False) -> bool: ...
    def set_speed(self, mps: float) -> None: ...  # DO_CHANGE_SPEED (AUTO) + WPNAV_SPEED (GUIDED)
    def log(self, tag: str, message: str) -> None: ...
