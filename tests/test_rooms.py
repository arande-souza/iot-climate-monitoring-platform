from datetime import datetime, timedelta, timezone

from test_sensor_routes import authenticated_client, sample_payload, setup_function, teardown_function


def room_payload(index=3, **changes):
    return {
        "name": f"Sala {index}", "device_id": f"esp32-sala-{index:02d}",
        "location": f"Bloco {index}", "description": "Ambiente de testes",
        "temperature_min": 20, "temperature_max": 26,
        "humidity_min": 30, "humidity_max": 65, "data_source": "simulation", **changes,
    }


def test_structured_location_edits_preserve_historical_location_and_device():
    with authenticated_client() as client:
        payload = room_payload(identifier="101", city=" São Paulo ", state="sp", internal_location="Estoque")
        room = client.post("/api/rooms", json=payload).json()
        assert room["city"] == "São Paulo" and room["state"] == "SP"
        reading = {**sample_payload(room["device_id"]), "location": "Referencia original da medicao", "co2": 2000}
        created = client.post("/api/readings", json=reading).json()
        timestamp = datetime.fromisoformat(created["created_at"].replace("Z", "+00:00"))
        brasilia = timezone(timedelta(hours=-3))
        filtered = client.get("/api/readings/history", params={
            "room_id": room["id"], "start": (timestamp - timedelta(minutes=1)).astimezone(brasilia).isoformat(),
            "end": (timestamp + timedelta(minutes=1)).astimezone(brasilia).isoformat(),
        })
        assert filtered.json()["total"] == 1
        payload.update(name="Sala renomeada", city="Campinas", internal_location="Escritorio", location="Referencia atual")
        updated = client.put(f"/api/rooms/{room['id']}", json=payload)
        assert updated.status_code == 200
        assert updated.json()["id"] == room["id"]
        assert updated.json()["device_id"] == room["device_id"]
        renamed = client.put(f"/api/rooms/{room['id']}", json=room_payload(name="Novo nome sem alterar cidade"))
        assert renamed.json()["city"] == "Campinas" and renamed.json()["identifier"] == "101"
        for path in ["history", "alerts"]:
            historical = client.get(f"/api/readings/{path}", params={"device_id": room["device_id"]}).json()["items"]
            assert historical[0]["id"] == created["id"]
            assert historical[0]["location"] == "Referencia original da medicao"
            export = client.get(f"/api/readings/{path}/export", params={"device_id": room["device_id"]})
            assert "Referencia original da medicao" in export.text
        assert client.post("/api/rooms", json=room_payload(4, state="Sao Paulo")).status_code == 422


def test_consolidated_history_weights_rooms_equally_and_separates_events():
    with authenticated_client() as client:
        registered = client.get("/api/rooms").json()
        room1, room2 = registered
        for room, temperature, humidity, co2 in [
            (room1, 20, 40, 750), (room1, 20, 40, 2000), (room2, 30, 80, 750),
        ]:
            data = {**sample_payload(room["device_id"]), "temperature": temperature,
                    "humidity": humidity, "co2": co2, "data_source": "sensor"}
            assert client.post("/api/readings", json=data).status_code == 201
        external = client.post("/api/rooms", json=room_payload(3, data_source="external_api")).json()
        client.post("/api/readings", json={**sample_payload(external["device_id"]), "temperature": 80, "data_source": "external_api"})
        from sqlalchemy import update
        from app.database import SessionLocal
        from app.models.sensor_reading import SensorReading
        with SessionLocal() as db:
            # Keep all three observations in one bucket, independent of test execution time.
            db.execute(update(SensorReading).values(created_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
            db.commit()
        response = client.get("/api/rooms/overview/history?days=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["series"]) == 1
        point = data["series"][0]
        assert point["temperature"] == 25 and point["humidity"] == 60
        assert point["count"] == 3 and point["room_count"] == 2
        assert point["alerts"] == 1 and point["critical"] == 1
        assert data["sources"] == {"sensor": 3}
        filtered = client.get("/api/rooms/overview/history", params={"room_id": room2["id"]}).json()["series"][0]
        assert filtered["temperature"] == 30 and filtered["room_count"] == 1
        assert filtered["alerts"] == 1 and filtered["critical"] == 0
        connectivity = client.get("/api/rooms/overview").json()
        assert connectivity["active_devices"] is None and connectivity["connectivity_available"] is False
        client.delete(f"/api/rooms/{room2['id']}?confirm=true")
        assert client.get("/api/rooms/overview/history", params={"room_id": room2["id"]}).status_code == 404
        assert client.get("/api/rooms/overview/history").json()["series"][0]["count"] == 2


def test_consolidated_history_has_no_fabricated_points_and_rejects_invalid_periods():
    with authenticated_client() as client:
        empty = client.get("/api/rooms/overview/history?days=30").json()
        assert empty["series"] == [] and empty["sources"] == {}
        assert client.get("/api/rooms/overview/history?days=0").status_code == 422
        assert client.get("/api/rooms/overview/history?room_id=missing").status_code == 404
        assert client.get("/api/rooms/overview/history", params={"start": "2026-08-11T00:00:00Z", "end": "2026-08-10T00:00:00Z"}).status_code == 422


def test_manual_update_all_rooms_includes_empty_rooms_and_skips_archived():
    with authenticated_client() as client:
        room3 = client.post("/api/rooms", json=room_payload(3, data_source="sensor")).json()
        deleted = client.post("/api/rooms", json=room_payload(4)).json()
        client.delete(f"/api/rooms/{deleted['id']}?confirm=true")
        response = client.post("/simulator/update-all-until-now", json={"frequency_seconds": 3600, "profile": "normal"})
        assert response.status_code == 200
        result = response.json()
        assert result["total_rooms"] == result["updated_rooms"] == 3
        assert result["total_generated"] == 75
        assert {row["room_id"] for row in result["rooms"]} == {room["id"] for room in client.get("/api/rooms").json()}
        for room in client.get("/api/rooms").json():
            latest = client.get("/api/readings/latest", params={"room_id": room["id"]}).json()
            assert latest[0]["data_source"] == "simulation"
            assert latest[0]["room_id"] == room["id"]
        assert client.get(f"/api/rooms/{room3['id']}").json()["data_source"] == "sensor"
        again = client.post("/simulator/update-all-until-now", json={"frequency_seconds": 3600})
        assert again.json()["total_generated"] == 0
        assert client.get("/api/readings/summary").json()["total_readings"] == 75
        assert client.post("/simulator/update-all-until-now", json={"frequency_seconds": True}).status_code == 422


def test_manual_update_all_rolls_back_if_any_room_fails(monkeypatch):
    from app.routes import simulator_routes
    import pytest

    original = simulator_routes.generate_simulated_readings
    calls = 0

    def fail_second(db, payload, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second room failed")
        return original(db, payload, **kwargs)

    with authenticated_client() as client:
        monkeypatch.setattr(simulator_routes, "generate_simulated_readings", fail_second)
        with pytest.raises(RuntimeError, match="second room failed"):
            client.post("/simulator/update-all-until-now", json={"frequency_seconds": 3600})
        assert client.get("/api/readings/summary").json()["total_readings"] == 0


def test_room_crud_and_ten_dynamic_rooms_preserve_existing_rooms():
    with authenticated_client() as client:
        initial = client.get("/api/rooms").json()
        assert {room["name"] for room in initial} == {"Sala 1", "Sala 2"}
        for index in range(3, 11):
            assert client.post("/api/rooms", json=room_payload(index)).status_code == 201
        rooms = client.get("/api/rooms").json()
        assert len(rooms) == 10
        room3 = next(room for room in rooms if room["name"] == "Sala 3")
        updated = client.put(f"/api/rooms/{room3['id']}", json=room_payload(name="Laboratório", temperature_max=24))
        assert updated.status_code == 200
        assert updated.json()["temperature_max"] == 24
        assert client.get("/api/rooms/overview").json()["total_rooms"] == 10
        comparison = client.get("/api/rooms/comparison?days=30")
        assert comparison.status_code == 200
        assert len(comparison.json()["rooms"]) == 10
        assert all(item["statistics"] is None for item in comparison.json()["rooms"])
        assert client.delete(f"/api/rooms/{room3['id']}").status_code == 400
        assert client.delete(f"/api/rooms/{room3['id']}?confirm=true").status_code == 204
        assert client.get(f"/api/rooms/{room3['id']}").status_code == 404
        assert len(client.get("/api/rooms").json()) == 9
        assert {room["id"] for room in initial}.issubset({room["id"] for room in client.get("/api/rooms").json()})


def test_room_limits_validation_and_unique_device_association():
    with authenticated_client() as client:
        assert client.post("/api/rooms", json=room_payload(temperature_min=28, temperature_max=20)).status_code == 422
        assert client.post("/api/rooms", json=room_payload(name="   ")).status_code == 422
        assert client.post("/api/rooms", json=room_payload(humidity_max=120)).status_code == 422
        assert client.post("/api/rooms", json=room_payload(source_config={"external_api_url": "bad-url"})).status_code == 422
        room = client.post("/api/rooms", json=room_payload()).json()
        assert client.post("/api/rooms", json=room_payload()).status_code == 409
        replacement = client.put(f"/api/rooms/{room['id']}", json=room_payload(device_id="other"))
        assert replacement.status_code == 200 and replacement.json()["id"] == room["id"]


def test_device_replacement_preserves_room_history_filters_and_exports():
    with authenticated_client() as client:
        room = client.post("/api/rooms", json=room_payload()).json()
        original = {**sample_payload(room["device_id"]), "co2": 2000, "location": "Local antigo"}
        first = client.post("/api/readings", json=original).json()
        replacement = client.put(f"/api/rooms/{room['id']}", json=room_payload(device_id="esp32-substituto")).json()
        second = client.post("/api/readings", json={**original, "device_id": replacement["device_id"], "location": "Local novo"}).json()
        assert first["room_id"] == second["room_id"] == room["id"]
        params = {"room_id": room["id"]}
        for path in ["history", "alerts"]:
            history = client.get(f"/api/readings/{path}", params=params)
            assert history.status_code == 200 and history.json()["total"] == 2
            ids = {item["device_id"] for item in history.json()["items"]}
            assert ids == {room["device_id"], "esp32-substituto"}
            exported = client.get(f"/api/readings/{path}/export", params=params)
            assert room["device_id"] in exported.text and "esp32-substituto" in exported.text
            filtered = client.get(f"/api/readings/{path}", params={**params, "device_id": room["device_id"]})
            assert filtered.json()["total"] == 1
        assert len(client.get("/api/readings/latest", params=params).json()) == 2
        assert client.get("/api/readings/summary", params=params).json()["total_readings"] == 2
        hours = client.get("/api/readings/alerts/critical-hours", params=params).json()
        assert sum(point["critico"] for point in hours) == 2
        assert client.post("/api/readings", json=original).status_code == 409
        assert client.post("/api/rooms", json=room_payload(4, device_id=room["device_id"])).status_code == 409


def test_room_deep_link_export_provenance_and_limit_edits():
    with authenticated_client() as client:
        room = client.post("/api/rooms", json=room_payload()).json()
        page = client.get(f"/rooms/{room['id']}")
        assert page.status_code == 200
        assert f'data-initial-room-id="{room["id"]}"' in page.text
        reading = {**sample_payload(room["device_id"]), "data_source": "simulation"}
        assert client.post("/api/readings", json=reading).status_code == 201
        assert client.get("/api/readings/status", params={"device_id": room["device_id"]}).json()["status"] == "ideal"
        assert client.put(f"/api/rooms/{room['id']}", json=room_payload(temperature_max=23)).status_code == 200
        assert client.get("/api/readings/status", params={"device_id": room["device_id"]}).json()["status"] == "alerta"
        export = client.get("/api/readings/history/export", params={"device_id": room["device_id"], "include_source": True})
        assert "Origem" in export.text and "simulation" in export.text
        # Historical classification is preserved when current room limits are edited.
        detail = client.get(f"/api/rooms/{room['id']}/dashboard").json()
        assert detail["status"] == "alerta" and detail["statistics"]["alerts"] == 0


def test_simulated_readings_do_not_claim_to_be_sensor_data():
    with authenticated_client() as client:
        room = client.post("/api/rooms", json=room_payload(data_source="sensor")).json()
        now = datetime.now(timezone.utc)
        result = client.post("/simulator/generate", json={
            "device_id": room["device_id"], "location": room["location"],
            "start_datetime": (now - timedelta(minutes=2)).isoformat(),
            "end_datetime": (now - timedelta(minutes=1)).isoformat(),
            "frequency_seconds": 60, "profile": "normal",
        })
        assert result.status_code == 200
        detail = client.get(f"/api/rooms/{room['id']}/dashboard").json()
        assert detail["room"]["data_source"] == "sensor"
        assert detail["latest_reading"]["data_source"] == "simulation"
        assert detail["sources"] == {"simulation": 2}


def test_room_statistics_isolation_sources_and_custom_thresholds():
    with authenticated_client() as client:
        narrow = client.post("/api/rooms", json=room_payload(3, temperature_max=23, data_source="sensor")).json()
        wide = client.post("/api/rooms", json=room_payload(4, temperature_max=30)).json()
        for room, source in [(narrow, "sensor"), (wide, "external_api")]:
            payload = {**sample_payload(room["device_id"]), "location": room["location"], "data_source": source}
            created = client.post("/api/readings", json=payload)
            assert created.status_code == 201
            assert created.json()["room_id"] == room["id"]
            assert created.json()["air_quality_status"] == ("alerta" if room == narrow else "ideal")
        response = client.get(f"/api/rooms/{narrow['id']}/dashboard?days=1")
        assert response.status_code == 200
        detail = response.json()
        assert detail["statistics"]["count"] == 1
        assert detail["statistics"]["temperature_avg"] == 23.5
        assert detail["statistics"]["alerts"] == 1
        assert detail["sources"] == {"sensor": 1}
        assert len(detail["series"]) == 1 and len(detail["alerts"]) == 1
        assert detail["monitoring_status"] == "atencao"
        assert detail["latest_reading"]["room_id"] == narrow["id"]
        overview = client.get("/api/rooms/overview").json()
        assert overview["valid_rooms"] == 1
        assert overview["external_reference_rooms"] == 1
        assert overview["average_sources"]["sensor"] == 1
        assert overview["counts"]["normal"] == 1 and overview["counts"]["atencao"] == 1
        assert overview["counts"]["sem_dados"] == 2
        assert overview["temperature_avg"] == 23.5
        comparison = client.get("/api/rooms/comparison").json()
        room_stats = {item["room"]["id"]: item for item in comparison["rooms"]}
        assert room_stats[wide["id"]]["statistics"]["alerts"] == 0
        assert room_stats[wide["id"]]["sources"] == {"external_api": 1}
        assert client.get(f"/api/rooms/{narrow['id']}/dashboard?days=0").status_code == 422
        assert client.get("/api/rooms/comparison", params={"start": "2026-10-02", "end": "2026-10-01"}).status_code == 422


def test_deleted_room_does_not_accept_ingestion_or_reappear_on_restart():
    from app.services.storage_service import initialize_storage

    with authenticated_client() as client:
        room = client.post("/api/rooms", json=room_payload()).json()
        reading = client.post("/api/readings", json=sample_payload(room["device_id"])).json()
        assert client.delete(f"/api/rooms/{room['id']}?confirm=true").status_code == 204
        assert client.post("/api/readings", json=sample_payload(room["device_id"])).status_code == 409
        assert client.get(f"/api/rooms/{room['id']}/dashboard").status_code == 404
        initialize_storage()
        assert room["id"] not in {item["id"] for item in client.get("/api/rooms").json()}
        assert client.get("/api/readings/latest").json()[0]["id"] == reading["id"]
        assert len(client.get("/api/rooms").json()) == 2


def test_room_without_data_and_stale_readings_are_not_fabricated():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        empty = client.get(f"/api/rooms/{room['id']}/dashboard").json()
        assert empty["series"] == [] and empty["statistics"] is None
        assert empty["latest_reading"] is None and empty["sources"] == {}
        now = datetime.now(timezone.utc)
        client.post("/simulator/generate", json={
            "device_id": room["device_id"], "location": room["location"],
            "start_datetime": (now - timedelta(days=2)).isoformat(),
            "end_datetime": (now - timedelta(days=2, minutes=-2)).isoformat(),
            "frequency_seconds": 60, "profile": "normal",
        })
        detail = client.get(f"/api/rooms/{room['id']}/dashboard?days=1").json()
        assert detail["series"] == [] and detail["stale"] is True
        assert detail["latest_reading"]["data_source"] == "simulation"
        history = client.get(f"/api/rooms/{room['id']}/dashboard?days=7").json()
        assert history["statistics"]["count"] == 3 and history["sources"] == {"simulation": 3}
        overview = client.get("/api/rooms/overview").json()
        assert overview["valid_rooms"] == 0 and overview["temperature_avg"] is None
        assert overview["counts"]["desatualizado"] == 1


def test_additive_migration_preserves_legacy_readings_and_is_idempotent(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from app.services import storage_service

    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy.begin() as connection:
        connection.execute(text('''CREATE TABLE sensor_readings (
            id INTEGER PRIMARY KEY, device_id VARCHAR(80), location VARCHAR(120),
            temperature FLOAT, humidity FLOAT, pressure FLOAT, co2 FLOAT, pm25 FLOAT,
            pm10 FLOAT, air_quality_status VARCHAR(20), created_at DATETIME
        )'''))
        connection.execute(text('''INSERT INTO sensor_readings VALUES (
            42, 'esp32-sala-01', 'Local original', 23, 50, 1013, 700, 8, 18,
            'ideal', '2026-08-10 03:00:00'
        )'''))
    monkeypatch.setattr(storage_service, "engine", legacy)
    storage_service.initialize_storage()
    storage_service.initialize_storage()
    with legacy.connect() as connection:
        row = connection.execute(text("SELECT * FROM sensor_readings")).mappings().one()
        assert row["id"] == 42 and row["temperature"] == 23
        assert row["room_id"] is not None and row["data_source"] == "unknown"
        assert connection.scalar(text("SELECT count(*) FROM rooms")) == 2
        assert connection.scalar(text("SELECT location FROM rooms WHERE device_id='esp32-sala-01'")) == "Local original"
    legacy.dispose()


def test_location_migration_keeps_existing_room_identity_and_free_text(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from app.services import storage_service

    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy_rooms.db'}")
    with legacy.begin() as connection:
        connection.execute(text('''CREATE TABLE rooms (
            id VARCHAR(36) PRIMARY KEY, name VARCHAR(120), description VARCHAR(1000),
            device_id VARCHAR(80) UNIQUE, location VARCHAR(120), temperature_min FLOAT,
            temperature_max FLOAT, humidity_min FLOAT, humidity_max FLOAT,
            data_source VARCHAR(20), source_config JSON, is_deleted BOOLEAN
        )'''))
        connection.execute(text('''INSERT INTO rooms VALUES (
            'original-id', 'Sala existente', 'Descricao original', 'esp32-sala-01',
            'Santo Andre - SP / Estoque', 19, 27, 35, 60, 'sensor', '{}', false
        )'''))
    monkeypatch.setattr(storage_service, "engine", legacy)
    storage_service.initialize_storage()
    storage_service.initialize_storage()
    with legacy.connect() as connection:
        room = connection.execute(text("SELECT * FROM rooms WHERE id='original-id'")).mappings().one()
        assert room["name"] == "Sala existente" and room["location"] == "Santo Andre - SP / Estoque"
        assert room["temperature_min"] == 19 and room["humidity_max"] == 60
        assert room["identifier"] == room["city"] == room["state"] == room["internal_location"] == ""
        assert connection.scalar(text("SELECT count(*) FROM schema_migrations WHERE version='room_locations_v2'")) == 1
    legacy.dispose()
