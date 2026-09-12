"""Which detections reach the submission table.

Ported from the acceptance rules in the team's outdoor FSM
(ChuanXiiiiii/IMAV-Competition `imav2026_outdoor_fsm.py::_capture_vehicle_records`), which only
counts a fix that is confident enough, accurate enough and labelled, and keys records on a stable id
so one vehicle seen twice is not submitted twice.

Two additions here: a rejected fix keeps the reason it was dropped, so nothing disappears silently,
and fixes of the same class within `merge_radius_m` are merged even when the detector gave them
different ids. Re-detecting the same truck on a second survey line is normal, and the rulebook
scores per vehicle (§5.4.1), so a duplicate row is a wrong answer, not a harmless one.

Pure functions, no I/O — see tests/unit/test_detection_filter.py.
"""

from __future__ import annotations

from typing import Any

from ..mission import geo

DEFAULTS = {
    "min_confidence": 0.5,
    "max_position_error_m": 5.0,
    "merge_radius_m": 10.0,
    "require_label": True,
}


def _settings(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out.update((cfg.get("detection") or {}).get("accept") or {})
    return out


def label_of(det: dict[str, Any]) -> str:
    """What goes in the 'Vehicle Identification' column: the read identity, else the class."""
    return str(det.get("ident") or det.get("cls") or "").strip()


def accept_detections(
    detections: list[dict[str, Any]], cfg: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split reported detections into (accepted, rejected).

    Each rejected row is a copy carrying `reason`. Accepted rows are in first-seen order, and a
    merged row carries `merged_from` listing the ids it absorbed.
    """
    s = _settings(cfg)
    min_conf = s.get("min_confidence")
    max_err = s.get("max_position_error_m")
    merge_radius = float(s.get("merge_radius_m") or 0.0)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    def reject(det: dict[str, Any], reason: str) -> None:
        rejected.append({**det, "reason": reason})

    for det in detections:
        lat, lon = det.get("lat"), det.get("lon")
        if lat is None or lon is None:
            reject(det, "no position")
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            reject(det, "position is not a number")
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            reject(det, "position out of range")
            continue
        if s.get("require_label", True) and not label_of(det):
            reject(det, "no class or identification")
            continue

        conf = det.get("conf")
        if min_conf is not None and conf is not None and float(conf) < float(min_conf):
            reject(det, f"confidence {float(conf):.2f} below {float(min_conf):.2f}")
            continue

        err = det.get("position_error_m")
        if max_err is not None and err is not None and float(err) > float(max_err):
            reject(det, f"position error {float(err):.1f} m above {float(max_err):.1f} m")
            continue

        det = {**det, "lat": lat, "lon": lon}

        # Same vehicle reported again: same id, or same class close by.
        twin = _find_twin(accepted, det, merge_radius)
        if twin is None:
            accepted.append(det)
            continue
        keeper, loser = _better(twin, det)
        loser_id = loser.get("id")
        merged = list(keeper.get("merged_from") or [])
        if loser_id is not None and loser_id != keeper.get("id"):
            merged.append(loser_id)
        keeper = {**keeper, "merged_from": merged} if merged else keeper
        accepted[accepted.index(twin)] = keeper
        reject(loser, f"duplicate of {keeper.get('id', label_of(keeper))}")

    return accepted, rejected


def _find_twin(
    accepted: list[dict[str, Any]], det: dict[str, Any], merge_radius_m: float
) -> dict[str, Any] | None:
    det_id = det.get("id")
    for other in accepted:
        if det_id is not None and other.get("id") == det_id:
            return other
        if merge_radius_m <= 0:
            continue
        if label_of(other) != label_of(det):
            continue
        if geo.distance_m((other["lat"], other["lon"]), (det["lat"], det["lon"])) <= merge_radius_m:
            return other
    return None


def _better(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep the more trustworthy of two reports: lower position error, then higher confidence."""
    a_err, b_err = a.get("position_error_m"), b.get("position_error_m")
    if a_err is not None and b_err is not None and float(a_err) != float(b_err):
        return (a, b) if float(a_err) < float(b_err) else (b, a)
    a_conf = float(a.get("conf") or 0.0)
    b_conf = float(b.get("conf") or 0.0)
    return (a, b) if a_conf >= b_conf else (b, a)
