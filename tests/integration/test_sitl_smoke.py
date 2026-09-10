"""Needs a running SITL (scripts/start_sitl.sh). Run with: pytest -m sitl"""

import socket

import pytest

from imav_m1.config import load_config

pytestmark = pytest.mark.sitl


def _reachable(connection: str) -> bool:
    try:
        _, host, port = connection.split(":")
        with socket.create_connection((host, int(port)), timeout=1):
            return True
    except OSError:
        return False


def test_sitl_heartbeat_and_mode():
    cfg = load_config("sim")
    conn = cfg["vehicle"]["connection"]
    if not _reachable(conn):
        pytest.skip(f"SITL not reachable at {conn} — start it with scripts/start_sitl.sh")
    from imav_m1.vehicle.mavlink_vehicle import MavlinkVehicle

    v = MavlinkVehicle(cfg)
    v.connect()
    try:
        v.drain()
        assert v.mode() != "UNKNOWN"
        assert v.armed() is False
        assert v.mission_count() >= 0
    finally:
        v.close()
