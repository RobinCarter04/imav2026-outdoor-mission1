import pytest

from imav_m1.mission import geo
from imav_m1.mission.area import load_area_inputs, parse_kml

SITE = (48.806567, 7.852134)

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Mapping Area 1</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
{a}
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Flight Area</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
{f}
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Landing</name><Point><coordinates>{l}</coordinates></Point></Placemark>
</Document></kml>"""


def _coords(poly):
    pts = list(poly) + [poly[0]]
    return " ".join(f"{lon},{lat},0" for lat, lon in pts)


def _with_survey(cfg, polygon, fence=None):
    out = dict(cfg)
    out["mission"] = dict(
        cfg["mission"], survey=dict(cfg["mission"]["survey"], area_polygon=polygon)
    )
    if fence is not None:
        out["safety"] = dict(cfg["safety"], geofence=dict(cfg["safety"]["geofence"], polygon=fence))
    return out


@pytest.fixture
def kml_file(tmp_path):
    area = geo.rectangle(SITE, 440, 280)
    fence = geo.rectangle(SITE, 800, 600)
    landing = geo.offset(SITE, -350, -250)
    p = tmp_path / "areas.kml"
    p.write_text(KML.format(a=_coords(area), f=_coords(fence), l=f"{landing[1]},{landing[0]},0"))
    return p


def test_parse_kml_swaps_to_lat_lon_and_drops_closing_point(kml_file):
    pms = parse_kml(kml_file)
    assert set(pms) == {"Mapping Area 1", "Flight Area", "Landing"}
    assert len(pms["Mapping Area 1"]) == 4
    lat, lon = pms["Landing"][0]
    assert 48 < lat < 49 and 7 < lon < 8


def test_load_from_kml(sim_cfg, kml_file):
    a = load_area_inputs(sim_cfg, kml_file)
    assert a.source.startswith("kml:") and len(a.survey) == 4 and len(a.fence) == 4
    assert a.landing is not None and geo.point_in_polygon(a.landing, a.fence)
    assert a.summary()["survey_area_ha"] == pytest.approx(12.32, abs=0.05)


def test_config_without_fence_falls_back_to_the_site_flight_area(sim_cfg):
    centre = geo.centroid([tuple(p) for p in sim_cfg["site"]["flight_area"]])
    cfg = _with_survey(sim_cfg, geo.rectangle(centre, 440, 280), fence=[])
    a = load_area_inputs(cfg)
    assert len(a.fence) == 4 and any("site 'imav'" in n for n in a.notes)


def test_sim_profile_area_is_inside_its_fence(sim_cfg):
    a = load_area_inputs(sim_cfg)
    assert a.summary()["survey_area_ha"] == pytest.approx(11.75, abs=0.2)  # Fig. 19 drawn area
    assert a.landing is not None


def test_survey_outside_fence_is_rejected(sim_cfg):
    far = geo.rectangle(geo.offset(SITE, 5000, 5000), 100, 100)
    with pytest.raises(ValueError, match="outside the fence"):
        load_area_inputs(_with_survey(sim_cfg, far))


def test_empty_survey_is_rejected(sim_cfg):
    with pytest.raises(ValueError, match="survey polygon"):
        load_area_inputs(_with_survey(sim_cfg, []))


def test_survey_touching_fence_passes_only_with_inset(sim_cfg):
    fence = geo.rectangle(SITE, 400, 300)
    touching = geo.rectangle(SITE, 400, 300)  # survey == fence: vertices on the boundary
    cfg = _with_survey(sim_cfg, touching, fence=fence)
    cfg["mission"]["survey"] = dict(cfg["mission"]["survey"], edge_margin_m=0)
    with pytest.raises(ValueError, match="outside the fence"):
        load_area_inputs(cfg)
    cfg["mission"]["survey"] = dict(cfg["mission"]["survey"], edge_margin_m=12)
    a = load_area_inputs(cfg)
    assert a.margin_m == 12 and len(a.survey_fly) == 4
    assert all(geo.point_in_polygon(p, fence) for p in a.survey_fly)
    assert a.summary()["fly_area_ha"] < a.summary()["survey_area_ha"]
    assert any("inset" in n for n in a.notes)


def test_fig19_kml_loads_and_plans(sim_cfg):
    from imav_m1.mission.survey import plan_survey

    a = load_area_inputs(sim_cfg, "sim/areas/haguenau_fig19.kml")
    assert a.source.startswith("kml:") and a.landing is not None
    assert (
        len(a.fence) == 4
    )  # the fence is the rulebook geofence; the traced flight zone is advisory
    plan = plan_survey(a.survey_fly, sim_cfg)
    assert plan.n_lines >= 6 and plan.est_time_s < 15 * 60


def test_both_sites_load_and_are_self_consistent():
    """Every site must plan a legal mission: area inside the fence, clear of exclusions."""
    from imav_m1.config import effective_max_alt_m, list_sites, load_config
    from imav_m1.mission.survey import plan_survey

    assert set(list_sites()) >= {"imav", "fenswood"}
    for site in list_sites():
        cfg = load_config("sim", site)
        a = load_area_inputs(cfg)
        assert a.site == site
        assert len(a.survey) >= 3 and len(a.fence) >= 3, site
        assert a.landing is not None and geo.point_in_polygon(a.landing, a.fence), site
        plan = plan_survey(a.survey_fly, cfg)
        assert plan.n_lines >= 2, site
        ceiling = effective_max_alt_m(cfg)
        assert cfg["mission"]["cruise_alt_m"] < ceiling, site
        for wp in plan.waypoints:
            assert geo.point_in_polygon((wp.lat, wp.lon), a.fence), (
                f"{site}: waypoint outside fence"
            )
            for z in a.exclusions:
                assert not geo.point_in_polygon((wp.lat, wp.lon), z["points"]), (
                    f"{site}: survey waypoint inside exclusion {z['name']}"
                )


def test_fenswood_carries_the_sar_sssi_exclusion_and_corridor():
    from imav_m1.config import effective_fence_action, effective_max_alt_m, load_config

    cfg = load_config("sim", "fenswood")
    a = load_area_inputs(cfg)
    assert [z["name"] for z in a.exclusions] == ["SSSI"]
    assert len(a.exclusions[0]["points"]) == 7
    assert len(a.transit_to_survey) == 4 and len(a.transit_to_home) == 4
    # the corridor exists precisely to stay out of the SSSI
    for wp in a.transit_to_survey + a.transit_to_home:
        assert not geo.point_in_polygon(wp, a.exclusions[0]["points"])
        assert geo.point_in_polygon(wp, a.fence)
    assert effective_max_alt_m(cfg) == 50.0  # tighter than the 75 m global cap
    assert effective_fence_action(cfg) == "rtl"
    assert cfg["mission"]["cruise_alt_m"] == 25.0


def test_a_site_cannot_raise_the_global_ceiling(tmp_path):
    import shutil

    from imav_m1.config import effective_max_alt_m, load_config

    cfgdir = tmp_path / "config"
    shutil.copytree("config", cfgdir)
    (cfgdir / "sites" / "greedy.yaml").write_text("site:\n  name: greedy\n  max_alt_m: 999\n")
    cfg = load_config("sim", "greedy", config_dir=cfgdir)
    assert cfg["site"]["max_alt_m"] == 999  # the file may ask
    assert effective_max_alt_m(cfg) == 75.0  # but the global cap still wins


def test_survey_overlapping_an_exclusion_is_rejected(sim_cfg):
    centre = geo.centroid([tuple(p) for p in sim_cfg["site"]["flight_area"]])
    cfg = _with_survey(sim_cfg, geo.rectangle(centre, 300, 200))
    cfg["site"] = dict(
        cfg["site"], exclusions=[{"name": "keep out", "points": geo.rectangle(centre, 400, 300)}]
    )
    with pytest.raises(ValueError, match="exclusion"):
        load_area_inputs(cfg)


# ── sites: exclusion zones and transit corridors ──────────────────────────────────────────────


def test_fenswood_site_loads_with_its_sssi_and_corridors():
    from imav_m1.config import load_config

    a = load_area_inputs(load_config("sim", "fenswood"))
    assert a.site == "fenswood"
    assert [z["name"] for z in a.exclusions] == ["SSSI"]
    assert len(a.transit_to_survey) == 4 and len(a.transit_to_home) == 4
    sssi = a.exclusions[0]["points"]
    # the whole reason the corridor exists: a straight run in would cut through the SSSI
    assert not any(geo.point_in_polygon(p, sssi) for p in a.survey_fly)
    assert not any(geo.point_in_polygon(p, sssi) for p in a.transit_to_survey + a.transit_to_home)
    assert all(geo.point_in_polygon(p, a.fence) for p in a.transit_to_survey)
    assert a.landing is not None and not geo.point_in_polygon(a.landing, sssi)

    straight = [
        (
            a.landing[0] + (a.survey_fly[0][0] - a.landing[0]) * i / 40,
            a.landing[1] + (a.survey_fly[0][1] - a.landing[1]) * i / 40,
        )
        for i in range(41)
    ]
    assert any(geo.point_in_polygon(p, sssi) for p in straight), (
        "expected the direct line to cross the SSSI"
    )


def test_survey_inside_an_exclusion_is_rejected(sim_cfg):
    from imav_m1.mission.area import validate_area_inputs

    fence = geo.rectangle(SITE, 600, 600)
    survey = geo.rectangle(SITE, 200, 200)
    with pytest.raises(ValueError, match="inside exclusion 'SSSI'"):
        validate_area_inputs(
            survey, fence, None, [{"name": "SSSI", "points": geo.rectangle(SITE, 300, 300)}]
        )


def test_transit_through_an_exclusion_is_rejected():
    from imav_m1.mission.area import validate_area_inputs

    fence = geo.rectangle(SITE, 900, 900)
    survey = geo.rectangle(geo.offset(SITE, 300, 300), 100, 100)
    zone = {"name": "SSSI", "points": geo.rectangle(SITE, 200, 200)}
    with pytest.raises(ValueError, match="transit waypoint"):
        validate_area_inputs(survey, fence, None, [zone], transit=[SITE])


def test_exclusions_can_come_from_a_kml(sim_cfg, tmp_path):
    area = geo.rectangle(SITE, 300, 200)
    fence = geo.rectangle(SITE, 900, 700)
    zone = geo.rectangle(geo.offset(SITE, 350, 0), 100, 100)
    body = KML.format(a=_coords(area), f=_coords(fence), l=f"{SITE[1]},{SITE[0]},0").replace(
        "</Document>",
        "<Placemark><name>SSSI</name><Polygon><outerBoundaryIs><LinearRing><coordinates>"
        f"{_coords(zone)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document>",
    )
    p = tmp_path / "with_exclusion.kml"
    p.write_text(body)
    a = load_area_inputs(sim_cfg, p)
    assert [z["name"] for z in a.exclusions] == ["SSSI"] and len(a.exclusions[0]["points"]) == 4
