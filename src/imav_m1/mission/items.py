"""Builders for MISSION_ITEM_INT sequences (no pymavlink)."""

from __future__ import annotations

from collections.abc import Sequence

from ..vehicle.interface import (
    MAV_CMD_DO_CHANGE_SPEED,
    MAV_CMD_NAV_LAND,
    MAV_CMD_NAV_TAKEOFF,
    MAV_CMD_NAV_WAYPOINT,
    MAV_FRAME_GLOBAL_RELATIVE_ALT,
    MAV_FRAME_MISSION,
    MissionItem,
    Waypoint,
)


def home_placeholder() -> MissionItem:
    """Seq 0 — ArduPilot overwrites it with the real home on arming."""
    return MissionItem(seq=0, command=MAV_CMD_NAV_WAYPOINT)


def change_speed(seq: int, mps: float) -> MissionItem:
    return MissionItem(
        seq=seq, command=MAV_CMD_DO_CHANGE_SPEED, frame=MAV_FRAME_MISSION, p1=1, p2=mps, p3=-1
    )


def waypoint(seq: int, wp: Waypoint, accept_radius_m: float = 2.0) -> MissionItem:
    return MissionItem(
        seq=seq,
        command=MAV_CMD_NAV_WAYPOINT,
        p2=accept_radius_m,
        lat=wp.lat,
        lon=wp.lon,
        alt=wp.alt_m,
    )


def takeoff(seq: int, alt_m: float) -> MissionItem:
    return MissionItem(seq=seq, command=MAV_CMD_NAV_TAKEOFF, alt=alt_m)


def land(seq: int, lat: float = 0.0, lon: float = 0.0, precision: int = 0) -> MissionItem:
    """p2 = precision-land mode (0 off, 1 opportunistic, 2 required) — placeholder for R-12."""
    return MissionItem(
        seq=seq,
        command=MAV_CMD_NAV_LAND,
        frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
        p2=precision,
        lat=lat,
        lon=lon,
        alt=0.0,
    )


def build_survey_mission(
    survey_wps: Sequence[Waypoint],
    speed_mps: float,
    landing: tuple[float, float] | None,
    cruise_alt_m: float,
    precision_land: int = 0,
) -> tuple[list[MissionItem], int, int]:
    """[home, DO_CHANGE_SPEED, survey..., (transit to landing), NAV_LAND].

    Returns (items, first_survey_seq, last_survey_seq) so the monitor knows where the survey ends.
    """
    items = [home_placeholder(), change_speed(1, speed_mps)]
    seq = 2
    first = seq
    for wp in survey_wps:
        items.append(waypoint(seq, wp))
        seq += 1
    last = seq - 1
    if landing is not None:
        items.append(waypoint(seq, Waypoint(landing[0], landing[1], cruise_alt_m)))
        seq += 1
        items.append(land(seq, landing[0], landing[1], precision_land))
    else:
        items.append(land(seq, 0.0, 0.0, precision_land))
    return items, first, last
