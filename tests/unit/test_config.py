from imav_m1.config import load_config


def test_overlay_merges_deeply(tmp_path):
    (tmp_path / "base.yaml").write_text("a: 1\nnested: {x: 1, y: 2}\n")
    (tmp_path / "sim.yaml").write_text("nested: {y: 3}\n")
    cfg = load_config("sim", tmp_path)
    assert cfg == {"a": 1, "nested": {"x": 1, "y": 3}, "profile": "sim"}


def test_missing_profile_is_an_error(tmp_path):
    (tmp_path / "base.yaml").write_text("a: 1\n")
    import pytest

    with pytest.raises(FileNotFoundError):
        load_config("nope", tmp_path)


def test_real_profiles_load_and_set_connection():
    for profile in ("sim", "hardware"):
        cfg = load_config(profile)
        assert cfg["profile"] == profile
        assert cfg["vehicle"]["connection"], f"{profile} must set vehicle.connection"
        assert cfg["camera"]["source"], f"{profile} must set camera.source"


def test_hardware_safety_is_never_looser_than_base():
    """ADR-002: hardware.yaml may only tighten safety values."""
    base = load_config("sim")["safety"]  # sim overlay doesn't touch safety → equals base
    hw = load_config("hardware")["safety"]
    assert hw["geofence"]["enabled"] is True
    assert hw["geofence"]["max_alt_m"] <= base["geofence"]["max_alt_m"]
    assert hw["battery_failsafe_pct"] >= base["battery_failsafe_pct"]
    assert hw["link_loss_timeout_s"] <= base["link_loss_timeout_s"]
    assert hw["require_operator_arm"] is True
