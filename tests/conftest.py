import pytest

from imav_m1.config import load_config
from imav_m1.vehicle import FakeVehicle


@pytest.fixture
def sim_cfg():
    return load_config("sim")


@pytest.fixture
def fake_vehicle():
    return FakeVehicle()
