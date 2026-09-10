import pytest

from imav_m1.config import load_config


def test_overlay_merges_deeply(tmp_path):
    (tmp_path / "base.yaml").write_text("a: 1\nnested: {x: 1, y: 2}\n")
    (tmp_path / "sim.yaml").write_text("nested: {y: 3}\n")
    cfg = load_config("sim", config_dir=tmp_path)
    assert cfg == {"a": 1, "nested": {"x": 1, "y": 3}, "profile": "sim"}


def test_missing_profile_is_an_error(tmp_path):
    (tmp_path / "base.yaml").write_text("a: 1\n")
    import pytest

    with pytest.raises(FileNotFoundError):
        load_config("nope", config_dir=tmp_path)


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


# ── site layer ────────────────────────────────────────────────────────────────────────────────


def test_list_sites_and_site_overlay():
    from imav_m1.config import list_sites

    assert set(list_sites()) >= {"imav", "fenswood"}
    imav, fens = load_config("sim", "imav"), load_config("sim", "fenswood")
    assert imav["site"]["name"] == "imav" and fens["site"]["name"] == "fenswood"
    # the site supplies the geometry, the profile still supplies the link
    assert imav["mission"]["survey"]["area_polygon"] != fens["mission"]["survey"]["area_polygon"]
    assert imav["vehicle"]["connection"] == fens["vehicle"]["connection"]
    assert fens["site"]["exclusions"] and not imav["site"]["exclusions"]
    assert len(fens["site"]["transit_to_survey"]) == 4


def test_default_site_comes_from_base():
    assert load_config("sim")["site"]["name"] == load_config("sim", "imav")["site"]["name"]


def test_unknown_site_is_an_error():
    with pytest.raises(FileNotFoundError, match="known sites"):
        load_config("sim", "nowhere")


def test_site_may_only_tighten_the_altitude_ceiling():
    """A site can lower the ceiling, never raise it above the global cap (rulebook §2: 80 m AGL)."""
    from imav_m1.config import effective_max_alt_m

    imav, fens = load_config("sim", "imav"), load_config("sim", "fenswood")
    cap = float(imav["safety"]["geofence"]["max_alt_m"])
    assert effective_max_alt_m(fens) == 50.0  # Fenswood R04, tighter than the cap
    assert effective_max_alt_m(imav) == cap
    for cfg in (imav, fens):
        assert effective_max_alt_m(cfg) <= cap
        assert cfg["mission"]["cruise_alt_m"] < effective_max_alt_m(cfg)

    greedy = dict(imav)
    greedy["site"] = dict(imav["site"], max_alt_m=500.0)
    assert effective_max_alt_m(greedy) == cap, "a site must not be able to raise the ceiling"


def test_site_fence_action_falls_back_to_the_global_default():
    from imav_m1.config import effective_fence_action

    assert effective_fence_action(load_config("sim", "fenswood")) == "rtl"  # site's own choice
    assert effective_fence_action(load_config("sim", "imav")) == "land"  # base default (§2)
