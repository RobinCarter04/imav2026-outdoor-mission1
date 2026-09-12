"""Many per-frame detections -> one row per vehicle.

PORTED FROM: SaR ``robin_package/passive_watch.py`` -- ``SmartEstimator`` (greedy tightest-cluster
consensus, median position, CEP50) and the weighting in ``DummyEstimator.add_observation``.

Two deliberate changes from the SaR original:

1. **Many targets, not one.** SaR locked onto a single casualty and then stopped accepting
   estimates. Mission 1 has several vehicles of different classes in one survey (rulebook Tab. 6),
   so observations are clustered by ground position instead of accumulated into one estimate.
2. **The clustering is the tracker.** On a nadir survey a vehicle's ground position is stationary
   while its image position sweeps across the frame, so associating in world coordinates is easier
   than in image space and gives de-duplication for free. No frame-to-frame tracker is needed, and
   the class label survives, which is where an image-space tracker tends to lose it.

Lock thresholds are not ported. SaR locked on 5 estimates agreeing within 1 m, which is reachable
while hovering over a target and is not from a single 60 m pass. Here every cluster is reported
(above ``min_observations``) with an honest error estimate, and ``detection/filter.py`` decides what
reaches the submission table.

Pure, no I/O. See tests/unit/test_aggregate.py.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..mission import geo

DEFAULTS = {
    "link_radius_m": 8.0,
    "min_observations": 2,
    "position_error_floor_m": 3.0,
}

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Observation:
    """One detection in one frame, already projected to the ground."""

    lat: float
    lon: float
    cls: str = UNKNOWN
    conf: float = 0.0
    t: float = 0.0
    quality: float = 0.5  # 0..1, higher is better; used to pick the representative frame
    image: str | None = None


@dataclass
class _Cluster:
    obs: list[Observation] = field(default_factory=list)
    lat: float = 0.0
    lon: float = 0.0

    def add(self, o: Observation) -> None:
        self.obs.append(o)
        self.lat = _median([x.lat for x in self.obs])
        self.lon = _median([x.lon for x in self.obs])

    @property
    def cls(self) -> str:
        named = [o.cls for o in self.obs if o.cls and o.cls != UNKNOWN]
        if not named:
            return UNKNOWN
        counts = Counter(named)
        top = max(counts.values())
        tied = [c for c, n in counts.items() if n == top]
        if len(tied) == 1:
            return tied[0]
        # Tie on count: the class carrying the most confident observation wins.
        return max(tied, key=lambda c: max(o.conf for o in self.obs if o.cls == c))

    @property
    def conf(self) -> float:
        cls = self.cls
        matching = [o.conf for o in self.obs if o.cls == cls] or [o.conf for o in self.obs]
        return max(matching)

    @property
    def best(self) -> Observation:
        return max(self.obs, key=lambda o: o.quality)

    def spread_m(self) -> float:
        """CEP-style: the median distance from the cluster centre. Ported from get_cep50()."""
        if len(self.obs) < 2:
            return 0.0
        return _median([geo.distance_m((self.lat, self.lon), (o.lat, o.lon)) for o in self.obs])


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out.update((cfg.get("detection") or {}).get("aggregate") or {})
    return out


class VehicleAggregator:
    """Collect projected detections, hand back one row per vehicle.

    Rows match the ``detections.jsonl`` contract in docs/DETECTION_INTERFACE.md, so they drop
    straight into ``accept_detections``.
    """

    def __init__(self, cfg: dict[str, Any] | None = None):
        s = settings(cfg or {})
        self.link_radius_m = float(s["link_radius_m"])
        self.min_observations = int(s["min_observations"])
        self.position_error_floor_m = float(s["position_error_floor_m"])
        self._clusters: list[_Cluster] = []

    def add(self, o: Observation) -> None:
        """Put one projected detection into the nearest compatible cluster, or start a new one."""
        best, best_d = None, self.link_radius_m
        for c in self._clusters:
            if not _same_vehicle_class(c.cls, o.cls):
                continue
            d = geo.distance_m((c.lat, c.lon), (o.lat, o.lon))
            if d <= best_d:
                best, best_d = c, d
        if best is None:
            best = _Cluster()
            self._clusters.append(best)
        best.add(o)

    def add_many(self, observations: list[Observation]) -> None:
        for o in observations:
            self.add(o)

    def vehicles(self) -> list[dict[str, Any]]:
        """One row per vehicle, in the order the vehicles were first seen."""
        return [
            self._row(c, i + 1)
            for i, c in enumerate(self._clusters)
            if len(c.obs) >= self.min_observations
        ]

    def dropped(self) -> list[dict[str, Any]]:
        """Clusters too thin to report, each carrying the reason. Log these; do not submit them."""
        out = []
        for i, c in enumerate(self._clusters):
            if len(c.obs) < self.min_observations:
                row = self._row(c, i + 1)
                row["reason"] = f"seen in {len(c.obs)} frame(s), needs {self.min_observations}"
                out.append(row)
        return out

    def _row(self, c: _Cluster, n: int) -> dict[str, Any]:
        best = c.best
        row: dict[str, Any] = {
            "t": round(best.t, 3),
            "lat": round(c.lat, 7),
            "lon": round(c.lon, 7),
            "cls": c.cls,
            "conf": round(c.conf, 3),
            "id": f"veh-{n}",
            "n_obs": len(c.obs),
            "position_error_m": round(max(c.spread_m(), self.position_error_floor_m), 2),
            "source": "aggregate",
        }
        if best.image:
            row["image"] = best.image
        return row


def _same_vehicle_class(a: str, b: str) -> bool:
    """Unknown matches anything: a box the model could not name is still evidence of a vehicle."""
    if not a or not b or a == UNKNOWN or b == UNKNOWN:
        return True
    return a == b


def _median(values: list[float]) -> float:
    if not values:
        return math.nan
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
