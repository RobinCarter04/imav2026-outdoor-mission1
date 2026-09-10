"""pymavlink implementation of the Vehicle protocol.

PORTED FROM: SaR sarFlightDay4/connection.py (DroneConnection) with the same hard-won behaviour:
  * lock on to the heartbeat from component 1 (MAV_COMP_ID_AUTOPILOT1) only — MAVProxy, ADS-B and
    other peripherals also send heartbeats and corrupt mode reads otherwise;
  * `drain()` pumps the whole receive queue every tick and keeps a private autopilot-only heartbeat
    cache; `mode()` / `armed()` read that cache (fast path);
  * mode changes are confirmed against autopilot heartbeats within a timeout, and the cache is
    updated on confirmation so the next tick does not see a stale mode ("false override" bug);
  * mission / fence uploads implement the MISSION_COUNT → REQUEST(_INT) → ITEM_INT → ACK handshake,
    filtering ACKs/requests by mission_type so fence and mission traffic don't cross;
  * mission progress is read from cached MISSION_CURRENT / MISSION_ITEM_REACHED; upload clears them.
This is the ONLY module allowed to import pymavlink (ADR-003; tests/unit/test_layout.py).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from .interface import (
    COPTER_MODE_NAMES,
    COPTER_MODES,
    MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION,
    MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION,
    MAV_FRAME_GLOBAL,
    FencePolygon,
    MissionItem,
    Telemetry,
)


class MavlinkVehicle:
    def __init__(self, cfg: dict[str, Any], status=None, logger=None):
        v = cfg["vehicle"]
        self.connection_string: str = v["connection"]
        self.baud: int = int(v.get("baud", 921600))
        self.mode_timeout_s: float = float(v.get("mode_change_timeout_s", 10))
        self.heartbeat_timeout_s: float = float(v.get("heartbeat_timeout_s", 10))
        self.autopilot_component: int = int(v.get("autopilot_component_id", 1))
        self.status = status  # SharedStatus (optional) — mirrors SaR
        self._logger = logger  # callable(tag, message) (optional)
        self.conn = None
        self._autopilot_hb = None

    # ── connection ────────────────────────────────────────────────────────────────────────────

    def connect(self) -> None:
        from pymavlink import mavutil

        self.log("INIT", f"Connecting to {self.connection_string} ...")
        self.conn = mavutil.mavlink_connection(
            self.connection_string, baud=self.baud, source_system=254
        )
        self._autopilot_hb = None
        self.log(
            "INIT", f"Waiting for autopilot heartbeat (component {self.autopilot_component}) ..."
        )
        deadline = time.time() + self.heartbeat_timeout_s * 6
        while True:
            hb = self.conn.recv_match(
                type="HEARTBEAT", blocking=True, timeout=self.heartbeat_timeout_s
            )
            if hb is None:
                if time.time() > deadline:
                    raise TimeoutError(f"no autopilot heartbeat on {self.connection_string}")
                self.log("INIT", "No heartbeat yet, retrying ...")
                continue
            if hb.get_srcComponent() != self.autopilot_component:
                continue
            self.conn.target_system = hb.get_srcSystem()
            self.conn.target_component = hb.get_srcComponent()
            self._autopilot_hb = hb
            break
        self.log(
            "INIT",
            f"Connected: system={self.conn.target_system} component={self.conn.target_component} "
            f"type={hb.type} mode={self.mode()}",
        )
        self._request_streams()
        if self.status:
            self.status.set_connected(True)

    def _request_streams(self) -> None:
        from pymavlink import mavutil

        m = mavutil.mavlink
        self.conn.mav.request_data_stream_send(
            self.conn.target_system, self.conn.target_component, m.MAV_DATA_STREAM_ALL, 4, 1
        )
        for msg_id, interval_us in [
            (m.MAVLINK_MSG_ID_GPS_RAW_INT, 250_000),
            (m.MAVLINK_MSG_ID_SYS_STATUS, 500_000),
            (m.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 250_000),
            (m.MAVLINK_MSG_ID_BATTERY_STATUS, 500_000),
            (m.MAVLINK_MSG_ID_VFR_HUD, 250_000),
            (m.MAVLINK_MSG_ID_MISSION_CURRENT, 500_000),
            (m.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 1_000_000),
        ]:
            self.conn.mav.command_long_send(
                self.conn.target_system,
                self.conn.target_component,
                m.MAV_CMD_SET_MESSAGE_INTERVAL,
                0,
                msg_id,
                interval_us,
                0,
                0,
                0,
                0,
                0,
            )

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self.status:
            self.status.set_connected(False)

    # ── receive pump + cached reads ───────────────────────────────────────────────────────────

    def drain(self) -> None:
        """Pump the receive queue until empty; keep the autopilot-only heartbeat cache fresh."""
        while True:
            msg = self.conn.recv_match(blocking=False)
            if msg is None:
                break
            if msg.get_type() == "HEARTBEAT" and self._is_autopilot(msg):
                self._autopilot_hb = msg
            elif msg.get_type() == "STATUSTEXT" and self._is_autopilot(msg):
                self.log("AP", msg.text)

    def _is_autopilot(self, msg) -> bool:
        return (
            msg.get_srcSystem() == self.conn.target_system
            and msg.get_srcComponent() == self.conn.target_component
        )

    def mode(self) -> str:
        hb = self._autopilot_hb
        if hb is None:
            return "UNKNOWN"
        name = COPTER_MODE_NAMES.get(hb.custom_mode, f"MODE_{hb.custom_mode}")
        if self.status:
            self.status.set_mode(name)
        return name

    def armed(self) -> bool | None:
        hb = self._autopilot_hb
        if hb is None:
            return None
        return bool(hb.base_mode & 128)  # MAV_MODE_FLAG_SAFETY_ARMED

    def telemetry(self) -> Telemetry:
        msgs = self.conn.messages
        t = Telemetry(timestamp_s=time.time())
        gps = msgs.get("GPS_RAW_INT")
        if gps:
            t.lat, t.lon = gps.lat / 1e7, gps.lon / 1e7
            t.alt_msl_m = gps.alt / 1000.0
            t.satellites, t.gps_fix = gps.satellites_visible, gps.fix_type
        pos = msgs.get("GLOBAL_POSITION_INT")
        if pos:
            t.lat, t.lon = pos.lat / 1e7, pos.lon / 1e7  # fused EKF position preferred
            t.alt_rel_m = pos.relative_alt / 1000.0
            t.heading_deg = pos.hdg / 100.0 if pos.hdg != 65535 else None
        hud = msgs.get("VFR_HUD")
        if hud:
            t.groundspeed_mps = hud.groundspeed
            if t.heading_deg is None:
                t.heading_deg = float(hud.heading)
        sys_status = msgs.get("SYS_STATUS")
        if sys_status:
            t.battery_v = sys_status.voltage_battery / 1000.0
            t.battery_pct = sys_status.battery_remaining
        ekf = msgs.get("EKF_STATUS_REPORT")
        if ekf:
            t.ekf_flags = ekf.flags
        return t

    # ── mode / arm / takeoff ──────────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> bool:
        from pymavlink import mavutil

        if mode not in COPTER_MODES:
            self.log("MODE", f"ERROR: unknown mode '{mode}'")
            return False
        target = COPTER_MODES[mode]
        if self._autopilot_hb is not None and self._autopilot_hb.custom_mode == target:
            self.log("MODE", f"Already in {mode}")
            return True
        self.log("MODE", f"{self.mode()} -> {mode} ...")
        self.conn.mav.set_mode_send(
            self.conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, target
        )
        deadline = time.time() + self.mode_timeout_s
        while time.time() < deadline:
            hb = self.conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            if hb is None or not self._is_autopilot(hb):
                continue
            self._autopilot_hb = hb  # keep cache current while we wait
            if hb.custom_mode == target:
                self.log("MODE", f"Confirmed: {mode}")
                if self.status:
                    self.status.set_mode(mode)
                return True
        self.log("MODE", f"TIMEOUT waiting for {mode}")
        return False

    def arm(self, timeout_s: float) -> bool:
        from pymavlink import mavutil

        self.conn.mav.command_long_send(
            self.conn.target_system,
            self.conn.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.drain()
            if self.armed() is True:
                return True
            time.sleep(0.2)
        return False

    def takeoff(self, alt_m: float) -> None:
        from pymavlink import mavutil

        self.conn.mav.command_long_send(
            self.conn.target_system,
            self.conn.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            float(alt_m),
        )

    # ── mission protocol ──────────────────────────────────────────────────────────────────────

    def _upload(
        self, items: list[dict], mission_type: int, tag: str, timeout: float = 20.0
    ) -> bool:
        from pymavlink import mavutil

        count = len(items)
        self.conn.mav.mission_count_send(
            self.conn.target_system, self.conn.target_component, count, mission_type=mission_type
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.conn.recv_match(
                type=["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"],
                blocking=True,
                timeout=2,
            )
            if msg is None:
                continue
            if getattr(msg, "mission_type", mission_type) != mission_type:
                continue
            if msg.get_type() == "MISSION_ACK":
                if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    self.log(tag, f"Upload complete — ACK ({count} items)")
                    return True
                self.log(tag, f"Upload REJECTED — ACK type {msg.type}")
                return False
            seq = msg.seq
            if not 0 <= seq < count:
                self.log(tag, f"ERROR: autopilot requested seq={seq} of 0..{count - 1}")
                return False
            it = items[seq]
            self.conn.mav.mission_item_int_send(
                self.conn.target_system,
                self.conn.target_component,
                seq,
                it["frame"],
                it["command"],
                0,
                it.get("autocontinue", 1),
                float(it.get("p1", 0)),
                float(it.get("p2", 0)),
                float(it.get("p3", 0)),
                float(it.get("p4", 0)),
                int(round(it["lat"] * 1e7)),
                int(round(it["lon"] * 1e7)),
                float(it["alt"]),
                mission_type=mission_type,
            )
        self.log(tag, "Upload TIMEOUT — no ACK")
        return False

    def upload_mission(self, items: Sequence[MissionItem]) -> bool:
        from pymavlink import mavutil

        raw = [
            {
                "frame": i.frame,
                "command": i.command,
                "p1": i.p1,
                "p2": i.p2,
                "p3": i.p3,
                "p4": i.p4,
                "lat": i.lat,
                "lon": i.lon,
                "alt": i.alt,
            }
            for i in items
        ]
        self.log("MISSION", f"Uploading {len(raw)} items ...")
        ok = self._upload(raw, mavutil.mavlink.MAV_MISSION_TYPE_MISSION, "MISSION")
        if ok:
            self.set_current_mission_item(0)
            self.clear_mission_progress_cache()
        return ok

    def upload_fence(self, polygons: Sequence[FencePolygon]) -> bool:
        from pymavlink import mavutil

        raw = []
        for poly in polygons:
            cmd = (
                MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION
                if poly.kind == "inclusion"
                else MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION
            )
            self.log("FENCE", f"  {poly.label or poly.kind}: {len(poly.points)} vertices")
            for lat, lon in poly.points:
                raw.append(
                    {
                        "frame": MAV_FRAME_GLOBAL,
                        "command": cmd,
                        "p1": len(poly.points),
                        "lat": lat,
                        "lon": lon,
                        "alt": 0.0,
                        "autocontinue": 0,
                    }
                )
        return self._upload(raw, mavutil.mavlink.MAV_MISSION_TYPE_FENCE, "FENCE")

    def _count(self, mission_type: int, timeout: float = 5.0) -> int:
        self.conn.mav.mission_request_list_send(
            self.conn.target_system, self.conn.target_component, mission_type=mission_type
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.conn.recv_match(type="MISSION_COUNT", blocking=True, timeout=2)
            if msg is None:
                continue
            if getattr(msg, "mission_type", mission_type) != mission_type:
                continue
            return msg.count
        return 0

    def mission_count(self) -> int:
        from pymavlink import mavutil

        return self._count(mavutil.mavlink.MAV_MISSION_TYPE_MISSION)

    def fence_count(self) -> int:
        from pymavlink import mavutil

        return self._count(mavutil.mavlink.MAV_MISSION_TYPE_FENCE)

    def mission_progress(self) -> tuple[int | None, int | None]:
        cur = self.conn.messages.get("MISSION_CURRENT")
        reached = self.conn.messages.get("MISSION_ITEM_REACHED")
        return (cur.seq if cur else None, reached.seq if reached else None)

    def set_current_mission_item(self, seq: int) -> None:
        self.conn.mav.mission_set_current_send(
            self.conn.target_system, self.conn.target_component, seq
        )

    def clear_mission_progress_cache(self) -> None:
        for key in ("MISSION_ITEM_REACHED", "MISSION_CURRENT"):
            self.conn.messages.pop(key, None)

    # ── params / speed ────────────────────────────────────────────────────────────────────────

    def set_param(self, name: str, value: float, wait: bool = False) -> bool:
        from pymavlink import mavutil

        pid = name.encode("utf-8").ljust(16, b"\x00")
        for attempt in range(3 if wait else 1):
            self.conn.mav.param_set_send(
                self.conn.target_system,
                self.conn.target_component,
                pid,
                float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            if not wait:
                return True
            deadline = time.time() + 4
            while time.time() < deadline:
                msg = self.conn.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
                if msg is None:
                    continue
                got = msg.param_id
                got = got.decode("utf-8") if isinstance(got, bytes) else got
                if got.rstrip("\x00") == name and abs(msg.param_value - float(value)) < 0.01:
                    return True
            self.log("PARAM", f"no confirmation for {name} (attempt {attempt + 1})")
        return False

    def set_speed(self, mps: float) -> None:
        from pymavlink import mavutil

        self.conn.mav.command_long_send(
            self.conn.target_system,
            self.conn.target_component,
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
            0,
            1,
            float(mps),
            -1,
            0,
            0,
            0,
            0,
        )
        self.set_param("WPNAV_SPEED", mps * 100.0)
        self.log("SPEED", f"{mps} m/s (DO_CHANGE_SPEED + WPNAV_SPEED)")

    # ── logging ───────────────────────────────────────────────────────────────────────────────

    def log(self, tag: str, message: str) -> None:
        if self._logger:
            self._logger(tag, message)
        else:
            print(f"  [{tag}] {message}  ({time.strftime('%H:%M:%S')})")
        if self.status:
            self.status.set_message(f"[{tag}] {message}")
