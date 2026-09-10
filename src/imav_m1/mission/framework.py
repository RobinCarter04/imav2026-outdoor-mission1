"""State-machine framework — PORTED FROM SaR sarFlightDay4/{machine.py, states/base.py, shared.py}.

Kept intact because it proved flexible and robust on the SaR flying days:
  * states are classes with enter() / execute() / exit(); execute() blocks until a transition
    condition is met and RETURNS THE NAME (string) of the next state;
  * the machine looks names up in a registry dict — states never import each other;
  * `shared` is a plain dict data bag passed between states; subroutine states (CHANGE_MODE,
    UPLOAD_MISSION, UPLOAD_FENCE, GENERATE_PATTERN) read `shared["return_to"]` and go back;
  * `SharedStatus` is the thread-safe bridge to the operator dashboard: the machine writes status,
    the dashboard writes commands ({"type": ...}) which states consume.
Changes from SaR: states receive a `MissionContext` (vehicle, cfg, shared, status, sleep, run_dir,
detector link, telemetry log) instead of (drone, shared), and time passes through `ctx.sleep()` so
unit tests can drive a FakeVehicle without waiting.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..vehicle.interface import Vehicle


class MachineStop(Exception):
    """Raised inside a blocking state when the machine is asked to stop."""


class SharedStatus:
    """Thread-safe store: state machine -> dashboard status, dashboard -> state machine commands."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current_state = "STARTING"
        self._current_mode = "UNKNOWN"
        self._transitioning = False
        self._last_message = ""
        self._connected = False
        self._last_update = 0.0
        self._pending: list[dict[str, Any]] = []
        self._extra: dict[str, Any] = {}
        self._log: list[str] = []

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            s = {
                "current_state": self._current_state,
                "current_mode": self._current_mode,
                "transitioning": self._transitioning,
                "last_message": self._last_message,
                "connected": self._connected,
                "last_update": self._last_update,
                "log_tail": self._log[-40:],
            }
            s.update(self._extra)
            return s

    def get_extra(self, key: str, default=None):
        with self._lock:
            return self._extra.get(key, default)

    def set_state(self, name: str, transitioning: bool = False) -> None:
        with self._lock:
            self._current_state, self._transitioning, self._last_update = (
                name,
                transitioning,
                time.time(),
            )

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._current_mode, self._last_update = mode, time.time()

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected, self._last_update = connected, time.time()

    def set_message(self, message: str) -> None:
        with self._lock:
            self._last_message, self._last_update = message, time.time()
            self._log.append(f"{time.strftime('%H:%M:%S')} {message}")
            if len(self._log) > 500:
                del self._log[:100]

    def set_extra(self, key: str, value: Any) -> None:
        with self._lock:
            self._extra[key] = value
            self._last_update = time.time()

    def send_command(self, command: dict[str, Any]) -> None:
        """Dashboard / scripts call this. Commands queue in order (SaR kept only the last one)."""
        with self._lock:
            self._pending.append(dict(command))

    def consume_command(self) -> dict[str, Any] | None:
        with self._lock:
            return self._pending.pop(0) if self._pending else None

    def peek_commands(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._pending)


@dataclass
class MissionContext:
    vehicle: Vehicle
    cfg: dict[str, Any]
    status: SharedStatus
    shared: dict[str, Any] = field(default_factory=dict)
    run_dir: Path = field(default_factory=lambda: Path("."))
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.time
    detector: Any = None  # detection.link.DetectorLink (optional)
    telemetry_log: Any = None  # mission.telemetry_log.TelemetryLog (optional)

    def log(self, tag: str, message: str) -> None:
        self.vehicle.log(tag, message)


class BaseState(ABC):
    """Rules (from SaR): execute() blocks until a transition; returns the next state's NAME;
    states never import/call other states; hardware only via ctx.vehicle; data via ctx.shared."""

    name = "UNNAMED"

    def __init__(self, ctx: MissionContext):
        self.ctx = ctx
        self.vehicle = ctx.vehicle
        self.cfg = ctx.cfg
        self.shared = ctx.shared
        self.status = ctx.status

    def log(self, message: str) -> None:
        self.vehicle.log(self.name, message)

    def sleep(self, seconds: float) -> None:
        if self.ctx.shared.get("_stop"):
            raise MachineStop
        self.ctx.sleep(seconds)

    def now(self) -> float:
        return self.ctx.clock()

    def consume_command(self) -> dict[str, Any] | None:
        return self.status.consume_command() if self.status else None

    def push(self, key: str, value: Any) -> None:
        if self.status:
            self.status.set_extra(key, value)

    def enter(self) -> None:  # noqa: B027 — optional hook
        pass

    @abstractmethod
    def execute(self) -> str: ...

    def exit(self) -> None:  # noqa: B027 — optional hook
        pass


class StateMachine:
    def __init__(
        self,
        ctx: MissionContext,
        registry: dict[str, type[BaseState]],
        initial: str,
        max_transitions: int | None = None,
    ):
        self.ctx = ctx
        self.registry = registry
        self.initial = initial
        self.current_name: str | None = None
        self.running = True
        self.max_transitions = max_transitions  # tests: stop runaway loops
        self.history: list[str] = []

    def stop(self) -> None:
        self.running = False
        self.ctx.shared["_stop"] = True

    def run(self) -> str | None:
        self.current_name = self.initial
        transitions = 0
        while self.running:
            cls = self.registry.get(self.current_name)
            if cls is None:
                self.ctx.log("MACHINE", f"FATAL: unknown state '{self.current_name}'")
                break
            state = cls(self.ctx)
            self.history.append(self.current_name)
            if self.ctx.status:
                self.ctx.status.set_state(self.current_name, transitioning=False)
            self.ctx.log("MACHINE", f"===== ENTER {self.current_name} =====")
            state.enter()
            try:
                next_name = state.execute()
            except MachineStop:
                state.exit()
                self.ctx.log("MACHINE", f"stop requested in {self.current_name}")
                break
            state.exit()
            if next_name not in self.registry:
                self.ctx.log(
                    "MACHINE", f"FATAL: '{self.current_name}' returned unknown state '{next_name}'"
                )
                break
            if next_name != self.current_name:
                self.ctx.log("MACHINE", f">>> {self.current_name} -> {next_name}")
                if self.ctx.status:
                    self.ctx.status.set_state(next_name, transitioning=True)
            self.current_name = next_name
            transitions += 1
            if self.ctx.shared.get("_stop"):
                break
            if self.max_transitions is not None and transitions >= self.max_transitions:
                self.ctx.log("MACHINE", "max transitions reached — stopping")
                break
        self.ctx.log("MACHINE", "Stopped")
        return self.current_name
