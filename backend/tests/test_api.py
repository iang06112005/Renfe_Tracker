import os
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app


def test_browser_does_not_call_renfe() -> None:
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    banned = ("gtfsrt.renfe.com", "ssl.renfe.com")
    offenders = [
        str(path)
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx", ".js", ".css"}
        and any(host in path.read_text(encoding="utf-8") for host in banned)
    ]
    assert offenders == []


def test_password_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import require_password

    monkeypatch.delenv("RENFE_TRACKER_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="RENFE_TRACKER_PASSWORD"):
        require_password()


def test_gtfs_failure_keeps_health_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> dict[str, bytes]:
        raise OSError("disco lleno")

    monkeypatch.setattr("gtfs_shapes.load_route_lines", explode)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        client.post("/api/login", json={"password": os.environ["RENFE_TRACKER_PASSWORD"]})
        lines = client.get("/api/lines")
        assert lines.status_code == 200
        assert lines.json() == {"type": "FeatureCollection", "features": []}


def test_boot_does_not_wait_for_gtfs(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    def slow() -> dict[str, bytes]:
        release.wait(15)
        from gtfs_shapes import _encode

        return _encode({})

    monkeypatch.setattr("gtfs_shapes.load_route_lines", slow)
    holder: dict[str, int] = {}

    def run() -> None:
        try:
            with TestClient(app) as client:
                holder["code"] = client.get("/api/health").status_code
        finally:
            release.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(5)
    release.set()
    assert holder.get("code") == 200
    thread.join(5)


def test_secure_cookie_when_proxy_is_https() -> None:
    password = os.environ["RENFE_TRACKER_PASSWORD"]
    with TestClient(app) as client:
        response = client.post(
            "/api/login",
            json={"password": password},
            headers={"x-forwarded-proto": "https"},
        )
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()


def test_health_login_and_live_trains() -> None:
    password = os.environ["RENFE_TRACKER_PASSWORD"]
    with TestClient(app) as client:
        client.timeout = httpx.Timeout(180)
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert client.get("/api/session").json() == {"authenticated": False}
        assert client.get("/api/trains").status_code == 401
        assert client.post("/api/login", json={"password": ""}).status_code == 422
        assert client.post("/api/login", json={"password": "no-es-la-clave"}).status_code == 401

        logged_in = client.post("/api/login", json={"password": password})
        assert logged_in.status_code == 200
        assert client.get("/api/session").json() == {"authenticated": True}

        all_trains = client.get("/api/trains")
        assert all_trains.status_code == 200
        assert "application/geo+json" in all_trains.headers["content-type"]
        assert all_trains.headers["cache-control"] == "no-store"
        body = all_trains.json()
        assert body["type"] == "FeatureCollection"
        if body["features"]:
            _assert_in_iberia(body["features"])
            assert "vehicleId" in body["features"][0]["properties"]

        cercanias = client.get("/api/trains?type=cercanias")
        assert cercanias.status_code == 200
        cercania_features = cercanias.json()["features"]
        assert all(feature["properties"]["service"] == "cercanias" for feature in cercania_features)
        if cercania_features:
            assert any(feature["properties"]["line"] for feature in cercania_features)
            assert any(feature["properties"]["platform"] for feature in cercania_features)

        larga = client.get("/api/trains?type=ld")
        assert larga.status_code == 200
        ld_features = larga.json()["features"]
        assert all(feature["properties"]["service"] == "ld" for feature in ld_features)

        assert client.get("/api/trains?type=nope").status_code == 422
        lines = client.get("/api/lines?type=cercanias")
        assert lines.status_code == 200
        assert "application/geo+json" in lines.headers["content-type"]
        line_body = lines.json()
        assert line_body["type"] == "FeatureCollection"
        assert line_body["features"]
        geometry = line_body["features"][0]["geometry"]
        assert geometry["type"] == "LineString"
        assert len(geometry["coordinates"]) >= 2
        _assert_in_iberia([{"geometry": {"coordinates": geometry["coordinates"][0]}}])
        assert line_body["features"][0]["properties"]["line"]
        assert str(line_body["features"][0]["properties"]["color"]).startswith("#")
        ld_lines = client.get("/api/lines?type=ld")
        assert ld_lines.status_code == 200
        assert ld_lines.json()["type"] == "FeatureCollection"
        metro_lines = client.get("/api/lines?type=metro")
        assert metro_lines.status_code == 200
        metro_body = metro_lines.json()
        assert metro_body["type"] == "FeatureCollection"
        if metro_body["features"]:
            assert metro_body["features"][0]["properties"]["service"] == "metro"
            assert metro_body["features"][0]["properties"]["line"]
            assert str(metro_body["features"][0]["properties"]["color"]).startswith("#")
        metro_stops = client.get("/api/stops?type=metro")
        assert metro_stops.status_code == 200
        assert metro_stops.json()["type"] == "FeatureCollection"
        assert client.get("/api/stops?type=nope").status_code == 422
        assert client.get("/api/lines?type=nope").status_code == 422

        assert client.post("/api/logout").status_code == 200
        assert client.get("/api/trains").status_code == 401
        assert client.get("/api/lines").status_code == 401
        assert client.get("/api/stops").status_code == 401
        assert client.get("/api/session").json() == {"authenticated": False}


def _assert_in_iberia(features: list[dict[str, object]]) -> None:
    for feature in features:
        geometry = feature["geometry"]
        assert isinstance(geometry, dict)
        coordinates = geometry["coordinates"]
        assert isinstance(coordinates, list)
        lon, lat = coordinates
        assert isinstance(lon, (int, float))
        assert isinstance(lat, (int, float))
        assert -20 <= lon <= 10
        assert 25 <= lat <= 52
