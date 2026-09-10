"""IDLE — PORTED FROM SaR states/idle.py, re-sequenced for Mission 1.

Ground state: monitor telemetry, store home, accept operator commands (dashboard, scripts or the
trigger file) and dispatch the setup chain. Nothing here arms or moves the aircraft.

Commands:
    load_area [kml]   load survey / fence / landing from config or a KML file
    plan              GENERATE_PATTERN (needs an area)
    upload            UPLOAD_FENCE → UPLOAD_MISSION (needs a plan)
    setup [kml]       load_area + plan + upload in one chain
    preflight         → PREFLIGHT_CHECK (needs upload)
    reset             forget plan/upload state
Trigger file (cfg operator.trigger_file): first word = command type, second = optional KML path.
"""

from __future__ import annotations

import os
from typing import Any

from ..area import load_area_inputs
from .common import MissionState


class IdleState(MissionState):
    name = "IDLE"

    def enter(self) -> None:
        self.log("IDLE — monitoring telemetry, awaiting operator commands")
        self.detector_mode("PASSIVE")

    def execute(self) -> str:
        while True:
            self.vehicle.drain()
            mode = self.vehicle.mode()
            t = self.vehicle.telemetry()
            if not self.shared.get("home") and t.has_position() and (t.gps_fix or 0) >= 3:
                self.shared["home"] = (t.lat, t.lon)
                self.log(f"Home position stored: {t.lat:.6f}, {t.lon:.6f}")
            self.push_telemetry()
            self.push(
                "idle",
                {
                    "mode": mode,
                    "home": self.shared.get("home"),
                    "area_loaded": "area" in self.shared,
                    "planned": "mission_items" in self.shared,
                    "fence_uploaded": bool(self.shared.get("fence_uploaded")),
                    "mission_uploaded": bool(self.shared.get("mission_uploaded")),
                    "last_error": self.shared.get("last_error"),
                },
            )
            cmd = self.consume_command() or self._read_trigger()
            if cmd:
                nxt = self._handle(cmd)
                if nxt:
                    return nxt
            self.sleep(self.tick())

    # ── commands ──────────────────────────────────────────────────────────────────────────────

    def _handle(self, cmd: dict[str, Any]) -> str | None:
        kind = cmd.get("type")
        self.shared.pop("last_error", None)
        if kind == "load_area":
            self._load_area(cmd.get("kml"))
            return None
        if kind == "plan":
            if "area" not in self.shared and not self._load_area(cmd.get("kml")):
                return None
            self.shared["return_to"] = "IDLE"
            return "GENERATE_PATTERN"
        if kind == "upload":
            if "mission_items" not in self.shared:
                return self._error("nothing to upload — run plan first")
            self.shared["return_stack"] = ["IDLE", "UPLOAD_MISSION"]
            return "UPLOAD_FENCE"
        if kind == "setup":
            if not self._load_area(cmd.get("kml")):
                return None
            self.shared["return_stack"] = ["IDLE", "UPLOAD_MISSION", "UPLOAD_FENCE"]
            return "GENERATE_PATTERN"
        if kind == "preflight":
            if not self.shared.get("mission_uploaded"):
                return self._error("mission not uploaded — run setup/upload first")
            return "PREFLIGHT_CHECK"
        if kind == "reset":
            self.clear_mission_keys()
            self.shared.pop("area", None)
            self.log("reset — plan and upload state cleared")
            return None
        if kind in ("abort", "pilot_ready", "start_mission", "cancel"):
            return None  # harmless here
        self.log(f"unknown command '{kind}' — ignoring")
        return None

    def _load_area(self, kml: str | None) -> bool:
        try:
            area = load_area_inputs(self.cfg, kml or self.shared.get("kml_path"))
        except Exception as e:  # noqa: BLE001 — surface any input problem to the operator
            self._error(f"area load failed: {e}")
            return False
        self.shared["area"] = area
        if kml:
            self.shared["kml_path"] = kml
        for n in area.notes:
            self.log(f"NOTE: {n}")
        self.log(f"Area loaded from {area.source}: {area.summary()}")
        self.push("area", area.summary())
        return True

    def _error(self, message: str) -> None:
        self.shared["last_error"] = message
        self.log(f"ERROR: {message}")
        return None

    def _read_trigger(self) -> dict[str, Any] | None:
        path = self.cfg.get("operator", {}).get("trigger_file")
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                parts = f.read().split()
            os.remove(path)
        except OSError as e:
            self.log(f"trigger file error: {e}")
            return None
        if not parts:
            return None
        cmd = {"type": parts[0].lower()}
        if len(parts) > 1:
            cmd["kml"] = parts[1]
        self.log(f"TRIGGER: {cmd}")
        return cmd
