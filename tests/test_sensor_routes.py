import csv
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace
import json
import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test_iot_climate.db"
os.environ["MQTT_ENABLED"] = "false"
os.environ["APP_USERNAME"] = "test-user"
os.environ["APP_PASSWORD"] = "test-password"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


def get_auth_headers() -> dict[str, str]:
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={"username": "test-user", "password": "test-password"},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}


def authenticated_client() -> TestClient:
    client = TestClient(app)
    client.headers.update(get_auth_headers())
    return client


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def sample_payload(device_id: str = "esp32-sala-01") -> dict:
    return {
        "device_id": device_id,
        "location": "Sala de TI",
        "temperature": 23.5,
        "humidity": 48.2,
        "pressure": 1012.4,
        "co2": 750,
        "pm25": 8.5,
        "pm10": 18.3,
    }


def test_rooms_keep_dashboard_history_alerts_and_exports_separate():
    with authenticated_client() as client:
        for device_id, location, profile, day in [
            ("esp32-sala-01", "Sala 1", "normal", "01"),
            ("esp32-sala-02", "Sala 2", "critical", "02"),
        ]:
            response = client.post("/simulator/generate", json={
                "device_id": device_id,
                "location": location,
                "profile": profile,
                "start_datetime": f"2026-10-{day}T12:00:00Z",
                "end_datetime": f"2026-10-{day}T12:02:00Z",
                "frequency_seconds": 60,
            })
            assert response.status_code == 200

        devices = client.get("/api/readings/devices")
        assert devices.status_code == 200
        assert devices.json() == [
            {"device_id": "esp32-sala-01", "location": "Sala 1"},
            {"device_id": "esp32-sala-02", "location": "Sala 2"},
        ]
        params = {"device_id": "esp32-sala-01"}
        latest = client.get("/api/readings/latest", params=params).json()
        assert len(latest) == 3
        assert all(row["device_id"] == params["device_id"] for row in latest)
        status = client.get("/api/readings/status", params=params).json()
        assert status["status"] == "ideal"
        assert status["latest_reading"]["device_id"] == params["device_id"]
        assert client.get("/api/readings/summary", params=params).json()["total_readings"] == 3
        assert client.get("/api/readings/summary").json()["total_readings"] == 6
        date_range = client.get("/api/readings/range", params=params).json()
        assert date_range["start_datetime"].startswith("2026-10-01T12:00:00")
        assert date_range["end_datetime"].startswith("2026-10-01T12:02:00")
        history = client.get("/api/readings/history", params=params).json()
        assert history["total"] == 3
        assert all(row["device_id"] == params["device_id"] for row in history["items"])
        assert client.get("/api/readings/alerts", params=params).json()["total"] == 0
        hours = client.get("/api/readings/alerts/critical-hours", params=params).json()
        assert sum(hour["total"] for hour in hours) == 0
        for path in ["history/export", "alerts/export"]:
            export = client.get(f"/api/readings/{path}", params=params)
            assert export.status_code == 200
            assert "esp32-sala-02" not in export.text
        room2 = {"device_id": "esp32-sala-02"}
        assert client.get("/api/readings/alerts", params=room2).json()["total"] > 0
        assert "esp32-sala-02" in client.get("/api/readings/alerts/export", params=room2).text

        empty = {"device_id": "sala-sem-dados"}
        assert client.get("/api/readings/status", params=empty).json()["latest_reading"] is None
        assert client.get("/api/readings/latest", params=empty).json() == []
        assert client.get("/api/readings/summary", params=empty).json()["total_readings"] == 0


def test_second_room_simulation_uses_its_own_last_reading():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload("esp32-sala-01"))
        response = client.post("/simulator/update-until-now", json={
            "device_id": "esp32-sala-02",
            "location": "Sala 2",
            "frequency_seconds": 3600,
            "profile": "normal",
        })
        assert response.status_code == 200
        assert response.json()["total_generated"] == 25
        assert client.get("/api/readings/summary", params={
            "device_id": "esp32-sala-01",
        }).json()["total_readings"] == 1
        again = client.post("/simulator/update-until-now", json={
            "device_id": "esp32-sala-02", "location": "Sala 2",
            "frequency_seconds": 3600, "profile": "normal",
        })
        assert again.json()["total_generated"] == 0


def test_mqtt_accepts_two_rooms_on_same_topic():
    from app.services.mqtt_service import _on_message

    for device_id, location in [("esp32-sala-01", "Sala 1"), ("esp32-sala-02", "Sala 2")]:
        payload = {**sample_payload(device_id), "location": location}
        _on_message(None, None, SimpleNamespace(
            topic="climate/readings", payload=json.dumps(payload).encode("utf-8"),
        ))
    with authenticated_client() as client:
        for device_id in ["esp32-sala-01", "esp32-sala-02"]:
            readings = client.get("/api/readings/latest", params={"device_id": device_id}).json()
            assert len(readings) == 1
            assert readings[0]["device_id"] == device_id


def test_rebuild_readings_backs_up_and_replaces_both_rooms(tmp_path):
    from scripts.reset_simulated_readings import rebuild_readings, parse_datetime

    with authenticated_client() as client:
        old = client.post("/api/readings", json=sample_payload("old-device")).json()
        start = parse_datetime("2026-08-10T00:00:00-03:00")
        end = start + timedelta(minutes=2)
        preview = rebuild_readings(start, end, backup_dir=tmp_path)
        assert preview["previous"] == 1
        assert not list(tmp_path.iterdir())
        result = rebuild_readings(start, end, backup_dir=tmp_path, apply=True)
        assert result["per_room"] == 3
        with result["backup"].open(encoding="utf-8-sig", newline="") as backup:
            rows = list(csv.DictReader(backup))
        assert len(rows) == 1
        assert rows[0]["device_id"] == "old-device"
        assert int(rows[0]["id"]) == old["id"]
        assert client.get("/api/readings/summary").json()["total_readings"] == 6
        assert client.get("/api/readings/latest", params={"device_id": "old-device"}).json() == []
        for device_id in ["esp32-sala-01", "esp32-sala-02"]:
            history = client.get("/api/readings/history", params={"device_id": device_id}).json()
            assert history["total"] == 3


def test_rebuild_readings_rolls_back_on_generation_failure(tmp_path, monkeypatch):
    from scripts import reset_simulated_readings as reset

    original_generate_values = reset.generate_values
    calls = 0

    def fail_generation(*args):
        nonlocal calls
        calls += 1
        if calls > 3:
            raise RuntimeError("generation failed")
        return original_generate_values(*args)

    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload("old-device"))
        start = reset.parse_datetime("2026-08-10T00:00:00-03:00")
        monkeypatch.setattr(reset, "generate_values", fail_generation)
        with pytest.raises(RuntimeError, match="generation failed"):
            reset.rebuild_readings(start, start + timedelta(minutes=2), backup_dir=tmp_path, apply=True)
        assert client.get("/api/readings/summary").json()["total_readings"] == 1
        assert client.get("/api/readings/latest").json()[0]["device_id"] == "old-device"
        assert len(list(tmp_path.glob("*.csv"))) == 1


def test_health_is_public_and_api_requires_authentication():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200

        protected = client.get("/api/readings/latest")
        assert protected.status_code == 401

        authenticated = client.get("/api/readings/latest", headers=get_auth_headers())
        assert authenticated.status_code == 200


def test_create_and_list_latest_reading():
    with authenticated_client() as client:
        response = client.post("/api/readings", json=sample_payload())
        assert response.status_code == 201
        created = response.json()
        assert created["air_quality_status"] == "ideal"

        latest = client.get("/api/readings/latest?limit=5")
        assert latest.status_code == 200
        assert len(latest.json()) == 1
        assert latest.json()[0]["device_id"] == "esp32-sala-01"


def test_rejects_invalid_payload():
    with authenticated_client() as client:
        payload = sample_payload()
        payload["temperature"] = None
        response = client.post("/api/readings", json=payload)
        assert response.status_code == 422

        payload = sample_payload()
        payload["temperature"] = "23.5"
        response = client.post("/api/readings", json=payload)
        assert response.status_code == 422


def test_filter_by_device_id():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload("esp32-sala-01"))
        client.post("/api/readings", json=sample_payload("esp32-lab-02"))

        response = client.get("/api/readings/device/esp32-lab-02")
        assert response.status_code == 200
        readings = response.json()
        assert len(readings) == 1
        assert readings[0]["device_id"] == "esp32-lab-02"


def test_history_by_period_and_environment_status():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload())

        start = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        history = client.get(f"/api/readings/history?start={start}&end={end}")
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert len(history.json()["items"]) == 1
        assert history.json()["page_size"] == 50

        status = client.get("/api/readings/status")
        assert status.status_code == 200
        assert status.json()["status"] == "ideal"


def test_history_can_return_all_readings_and_date_range():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload("esp32-sala-01"))
        client.post("/api/readings", json=sample_payload("esp32-lab-02"))

        history = client.get("/api/readings/history")
        assert history.status_code == 200
        assert history.json()["total"] == 2
        assert len(history.json()["items"]) == 2

        date_range = client.get("/api/readings/range")
        assert date_range.status_code == 200
        assert date_range.json()["start_datetime"] is not None
        assert date_range.json()["end_datetime"] is not None

        summary = client.get("/api/readings/summary")
        assert summary.status_code == 200
        assert summary.json()["total_readings"] == 2


def test_history_pagination_accepts_expected_page_sizes():
    with authenticated_client() as client:
        for index in range(55):
            client.post("/api/readings", json=sample_payload(f"esp32-{index:02d}"))

        response = client.get("/api/readings/history?page=1&page_size=20")
        assert response.status_code == 200
        assert response.json()["total"] == 55
        assert len(response.json()["items"]) == 20
        assert response.json()["total_pages"] == 3

        response = client.get("/api/readings/history?page=1&page_size=50")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 50

        response = client.get("/api/readings/history?page=1&page_size=200")
        assert response.status_code == 200
        assert response.json()["page_size"] == 200
        assert len(response.json()["items"]) == 55

        response = client.get("/api/readings/history?page=1&page_size=25")
        assert response.status_code == 422


def test_history_filters_by_status():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload("esp32-ideal-01"))

        alert_payload = sample_payload("esp32-alerta-01")
        alert_payload["temperature"] = 29.2
        client.post("/api/readings", json=alert_payload)

        response = client.get("/api/readings/history?status_filter=alerta")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["air_quality_status"] == "alerta"


def test_history_export_csv_uses_applied_filters_and_grid_columns():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload("esp32-ideal-01"))

        alert_payload = sample_payload("esp32-alerta-01")
        alert_payload["temperature"] = 29.2
        client.post("/api/readings", json=alert_payload)

        response = client.get("/api/readings/history/export?status_filter=alerta")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")

        rows = list(csv.reader(StringIO(response.text.lstrip("\ufeff"))))
        assert rows[0] == [
            "Data",
            "Dispositivo",
            "Local",
            "Temp.",
            "Umid.",
            "Pressao",
            "CO2",
            "PM2.5",
            "PM10",
            "Status",
        ]
        assert len(rows) == 2
        assert rows[1][1] == "esp32-alerta-01"
        assert rows[1][9] == "alerta"


def test_alert_history_returns_only_alert_and_critical_readings():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload())

        alert_payload = sample_payload("esp32-alerta-01")
        alert_payload["temperature"] = 29.2
        alert_payload["co2"] = 1180
        client.post("/api/readings", json=alert_payload)

        critical_payload = sample_payload("esp32-critico-01")
        critical_payload["co2"] = 1800
        critical_payload["pm25"] = 48.0
        client.post("/api/readings", json=critical_payload)

        start = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        response = client.get(f"/api/readings/alerts?start={start}&end={end}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        statuses = {reading["air_quality_status"] for reading in data["items"]}
        assert statuses == {"alerta", "critico"}

        critical_hours = client.get(f"/api/readings/alerts/critical-hours?start={start}&end={end}")
        assert critical_hours.status_code == 200
        assert len(critical_hours.json()) == 24
        assert sum(item["alerta"] for item in critical_hours.json()) == 1
        assert sum(item["critico"] for item in critical_hours.json()) == 1
        assert sum(item["total"] for item in critical_hours.json()) == 2

        filtered_alerts = client.get(
            f"/api/readings/alerts?start={start}&end={end}&alert_type=critico"
        )
        assert filtered_alerts.status_code == 200
        assert filtered_alerts.json()["total"] == 1
        assert filtered_alerts.json()["items"][0]["air_quality_status"] == "critico"

        filtered_hours = client.get(
            f"/api/readings/alerts/critical-hours?start={start}&end={end}&alert_type=alerta"
        )
        assert filtered_hours.status_code == 200
        assert sum(item["alerta"] for item in filtered_hours.json()) == 1
        assert sum(item["critico"] for item in filtered_hours.json()) == 0


def test_alert_export_csv_uses_applied_filters_and_grid_columns():
    with authenticated_client() as client:
        client.post("/api/readings", json=sample_payload())

        alert_payload = sample_payload("esp32-alerta-01")
        alert_payload["temperature"] = 29.2
        alert_payload["co2"] = 1180
        client.post("/api/readings", json=alert_payload)

        critical_payload = sample_payload("esp32-critico-01")
        critical_payload["co2"] = 1800
        critical_payload["pm25"] = 48.0
        client.post("/api/readings", json=critical_payload)

        response = client.get("/api/readings/alerts/export?alert_type=critico")
        assert response.status_code == 200

        rows = list(csv.reader(StringIO(response.text.lstrip("\ufeff"))))
        assert rows[0] == [
            "Data",
            "Dispositivo",
            "Local",
            "Temp.",
            "Umid.",
            "CO2",
            "PM2.5",
            "PM10",
            "Status",
        ]
        assert len(rows) == 2
        assert rows[1][1] == "esp32-critico-01"
        assert rows[1][8] == "critico"


def test_simulator_generate_creates_historical_readings():
    with authenticated_client() as client:
        payload = {
            "device_id": "esp32-sala-01",
            "location": "Santo André - SP",
            "start_datetime": "2026-03-16T08:00:00",
            "end_datetime": "2026-03-16T08:05:00",
            "frequency_seconds": 60,
            "profile": "mixed",
        }

        response = client.post("/simulator/generate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_generated"] == 6
        assert data["device_id"] == "esp32-sala-01"
        assert data["location"] == "Santo André - SP"

        latest = client.get("/api/readings/latest?limit=10")
        assert latest.status_code == 200
        assert len(latest.json()) == 6


def test_simulator_validates_date_range_frequency_and_limit():
    with authenticated_client() as client:
        payload = {
            "device_id": "esp32-sala-01",
            "location": "Santo André - SP",
            "start_datetime": "2026-03-16T18:00:00",
            "end_datetime": "2026-03-16T08:00:00",
            "frequency_seconds": 60,
            "profile": "normal",
        }
        assert client.post("/simulator/generate", json=payload).status_code == 400

        payload["start_datetime"] = "2026-03-16T08:00:00"
        payload["end_datetime"] = "2026-03-16T18:00:00"
        payload["frequency_seconds"] = 0
        assert client.post("/simulator/generate", json=payload).status_code == 422

        payload["frequency_seconds"] = 1
        payload["end_datetime"] = "2026-03-18T12:00:00"
        assert client.post("/simulator/generate", json=payload).status_code == 400


def test_simulator_update_until_now_generates_from_last_reading():
    with authenticated_client() as client:
        payload = sample_payload()
        client.post("/api/readings", json=payload)

        response = client.post(
            "/simulator/update-until-now",
            json={
                "device_id": "esp32-sala-01",
                "location": "Santo André - SP",
                "frequency_seconds": 3600,
                "profile": "normal",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["total_generated"] >= 0


def test_simulator_update_until_now_returns_no_data_when_current():
    with authenticated_client() as client:
        response = client.post(
            "/simulator/generate",
            json={
                "device_id": "esp32-sala-01",
                "location": "Santo André - SP",
                "start_datetime": datetime.now(timezone.utc).isoformat(),
                "end_datetime": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
                "frequency_seconds": 60,
                "profile": "normal",
            },
        )
        assert response.status_code == 200

        response = client.post(
            "/simulator/update-until-now",
            json={
                "device_id": "esp32-sala-01",
                "location": "Santo André - SP",
                "frequency_seconds": 60,
                "profile": "normal",
            },
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Coleta atualizada, aguarde pelo menos 60s"
        assert response.json()["total_generated"] == 0
