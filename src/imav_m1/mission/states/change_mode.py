"""CHANGE_MODE — PORTED FROM SaR states/change_mode.py. Subroutine: set shared["requested_mode"]."""

from __future__ import annotations

from .common import MissionState


class ChangeModeState(MissionState):
    name = "CHANGE_MODE"

    def execute(self) -> str:
        target = self.shared.pop("requested_mode", None)
        return_to = self.return_next("IDLE")
        if target is None:
            self.log(f"ERROR: no mode requested — returning to {return_to}")
            return return_to
        ok = self.vehicle.set_mode(target)
        self.shared["last_mode_change_ok"] = ok
        self.log(
            f"Mode change to {target} {'SUCCEEDED' if ok else 'FAILED'} — returning to {return_to}"
        )
        return return_to
