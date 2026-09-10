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
    transit_to_survey: Sequence[tuple[float, float]] = (),
    transit_to_home: Sequence[tuple[float, float]] = (),
    transit_speed_mps: float | None = None,
) -> tuple[list[MissionItem], int, int]:
    """The whole flight as one AUTO mission:

        home, DO_CHANGE_SPEED, [corridor out], (DO_CHANGE_SPEED), survey lines,
        [corridor home], transit to the landing point, NAV_LAND

    The corridors are the SaR SSSI_NAV_TO_SEARCH / SSSI_NAV_TO_HOME idea: named waypoints that route
    around an exclusion zone instead of cutting straight across it. They fly at `transit_speed_mps`
    when one is given, and the speed drops back to `speed_mps` for the survey itself.

    Returns (items, first_survey_seq, last_survey_seq) so the monitor knows where the survey ends.
    """
    transit_speed = float(transit_speed_mps) if transit_speed_mps else float(speed_mps)
    items = [home_placeholder(), change_speed(1, transit_speed)]
    seq = 2

    def add_leg(points: Sequence[tuple[float, float]]) -> None:
        nonlocal seq
        for lat, lon in points:
            items.append(waypoint(seq, Waypoint(float(lat), float(lon), cruise_alt_m)))
            seq += 1

    add_leg(transit_to_survey)
    if transit_speed != float(speed_mps):
        items.append(change_speed(seq, float(speed_mps)))
        seq += 1

    first = seq
    for wp in survey_wps:
        items.append(waypoint(seq, wp))
        seq += 1
    last = seq - 1

    if transit_speed != float(speed_mps) and transit_to_home:
        items.append(change_speed(seq, transit_speed))
        seq += 1
    add_leg(transit_to_home)

    if landing is not None:
        items.append(waypoint(seq, Waypoint(landing[0], landing[1], cruise_alt_m)))
        seq += 1
        items.append(land(seq, landing[0], landing[1], precision_land))
    else:
        items.append(land(seq, 0.0, 0.0, precision_land))
    return items, first, last
