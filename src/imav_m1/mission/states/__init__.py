"""State registry — PORTED FROM SaR states/__init__.py. The ONLY place that imports state classes.

Mission 1 flow (fully autonomous after the operator presses START in PREFLIGHT_CHECK):

    IDLE ─setup→ GENERATE_PATTERN → UPLOAD_FENCE → UPLOAD_MISSION → IDLE
    IDLE ─preflight→ PREFLIGHT_CHECK ─start_mission→ TAKEOFF → SURVEY → RETURN_LAND → REPORT → DONE
    any airborne state ─abort / failsafe / pilot override timeout→ ABORT → REPORT → DONE

Subroutines (return via shared["return_to"] or the return stack): CHANGE_MODE, UPLOAD_MISSION,
UPLOAD_FENCE, GENERATE_PATTERN.
"""

from .abort import AbortState
from .change_mode import ChangeModeState
from .done import DoneState
from .generate_pattern import GeneratePatternState
from .idle import IdleState
from .preflight_check import PreflightCheckState
from .report import ReportState
from .return_land import ReturnLandState
from .survey import SurveyState
from .takeoff import TakeoffState
from .upload_fence import UploadFenceState
from .upload_mission import UploadMissionState

STATE_CLASSES = {
    # operational
    "IDLE": IdleState,
    "PREFLIGHT_CHECK": PreflightCheckState,
    "TAKEOFF": TakeoffState,
    "SURVEY": SurveyState,
    "RETURN_LAND": ReturnLandState,
    "REPORT": ReportState,
    "DONE": DoneState,
    "ABORT": AbortState,
    # subroutines
    "CHANGE_MODE": ChangeModeState,
    "UPLOAD_MISSION": UploadMissionState,
    "UPLOAD_FENCE": UploadFenceState,
    "GENERATE_PATTERN": GeneratePatternState,
}

INITIAL_STATE = "IDLE"
