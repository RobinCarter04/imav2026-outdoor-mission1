"""Operator dashboard HTTP surface: operator commands and the detector POST route."""

from __future__ import annotations

import json

import pytest

from imav_m1.detection.link import DetectorLink
from imav_m1.mission.framework import SharedStatus
from imav_m1.ops.dashboard import create_app


@pytest.fixture
def client(tmp_path):
    status = SharedStatus()
    app = create_app(status, tmp_path)
    app.config.update(TESTING=True)
    return app.test_client(), status, tmp_path


def test_command_endpoint_queues_operator_commands(client):
    c, status, _ = client
    assert c.post("/api/command", json={"type": "resume"}).get_json()["ok"] is True
    assert status.consume_command() == {"type": "resume"}
    bad = c.post("/api/command", json={})
    assert bad.status_code == 400 and bad.get_json()["ok"] is False


def test_detection_endpoint_appends_the_same_line_the_file_route_would(client):
    c, _, run_dir = client
    det = {
        "lat": 48.8095202,
        "lon": 7.8520274,
        "cls": "CCF",
        "ident": "67-CCF-M-ING",
        "id": "veh-3",
    }
    assert c.post("/api/detection", json=det).get_json()["ok"] is True

    rows = DetectorLink(run_dir).read_detections()
    assert len(rows) == 1
    row = rows[0]
    assert row["cls"] == "CCF" and row["ident"] == "67-CCF-M-ING" and row["id"] == "veh-3"
    assert row["lat"] == pytest.approx(48.8095202) and row["source"] == "http"
    assert isinstance(row["t"], float), "the endpoint fills in the timestamp"
    # one JSON object per line, exactly as a detector writing the file directly would produce
    lines = (run_dir / "detections" / "detections.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["cls"] == "CCF"


@pytest.mark.parametrize(
    "payload, why",
    [
        ({"lon": 7.85, "cls": "CCF"}, "lat"),
        ({"lat": 48.8, "cls": "CCF"}, "lon"),
        ({"lat": 48.8, "lon": 7.85}, "cls"),
        ({"lat": "over there", "lon": 7.85, "cls": "CCF"}, "numbers"),
    ],
)
def test_detection_endpoint_rejects_unusable_reports(client, payload, why):
    c, _, run_dir = client
    r = c.post("/api/detection", json=payload)
    assert r.status_code == 400, why
    assert DetectorLink(run_dir).read_detections() == []


def test_status_endpoint_exposes_what_the_page_polls(client):
    c, status, _ = client
    status.set_state("SURVEY")
    status.set_extra("override", {"paused": True, "mode": "LOITER", "can_resume": False})
    s = c.get("/api/status").get_json()
    assert s["current_state"] == "SURVEY"
    assert s["override"]["can_resume"] is False
