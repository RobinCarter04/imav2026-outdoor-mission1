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


def test_config_without_fence_falls_back_to_site_geofence(sim_cfg):
    centre = geo.centroid([tuple(p) for p in sim_cfg["site"]["geofence_corners"]])
    cfg = _with_survey(sim_cfg, geo.rectangle(centre, 440, 280), fence=[])
    a = load_area_inputs(cfg)
    assert len(a.fence) == 4 and any("SITE geofence" in n for n in a.notes)


def test_sim_profile_area_is_inside_its_fence(sim_cfg):
    a = load_area_inputs(sim_cfg)
    assert a.summary()["survey_area_ha"] == pytest.approx(12.32, abs=0.1)
    assert a.landing is not None


def test_survey_outside_fence_is_rejected(sim_cfg):
    far = geo.rectangle(geo.offset(SITE, 5000, 5000), 100, 100)
    with pytest.raises(ValueError, match="outside the fence"):
        load_area_inputs(_with_survey(sim_cfg, far))


def test_empty_survey_is_rejected(sim_cfg):
    with pytest.raises(ValueError, match="survey polygon"):
        load_area_inputs(_with_survey(sim_cfg, []))
