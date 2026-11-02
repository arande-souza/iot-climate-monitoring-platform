from decimal import Decimal

from test_sensor_routes import authenticated_client, sample_payload, setup_function, teardown_function


def scenario_payload(room_id, **changes):
    # Values are confined to tests; the product never pre-fills prices or consumption.
    return {"room_id": room_id, "name": "Caso de teste A", "equipment_model": "Equipamento de teste",
            "cooling_capacity_btu_h": 12000, "method": "power", "average_power_kw": "1.2",
            "equipment_price": "2400.00", "installation_cost": "600.00",
            "hours_per_day": "8", "days_per_month": 22, "tariff_per_kwh": "0.90",
            "parameter_source": "Parâmetros exclusivos de teste", **changes}


def test_power_estimate_uses_kw_hours_and_tariff_and_does_not_save():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        response = client.post("/api/costs/estimate", json=scenario_payload(room["id"]))
        assert response.status_code == 200
        result = response.json()["results"]
        assert result["monthly_energy_kwh"] == "211.2000"
        assert result["monthly_cost"] == "190.08"
        assert result["annual_cost"] == "2280.96"
        assert result["initial_investment"] == "3000.00"
        assert result["projections"][2]["total_cost"] == "9842.88"
        assert len(result["series"]) == 37
        assert result["series"][0]["total_cost"] == "3000.00"
        assert result["series"][0]["energy_cost"] == "0.00"
        assert client.get("/api/costs/scenarios", params={"room_id": room["id"]}).json() == []


def test_costs_are_independent_of_btu_and_environmental_measurements():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        first = client.post("/api/costs/estimate", json=scenario_payload(room["id"])).json()["results"]
        client.post("/api/readings", json={**sample_payload(room["device_id"]), "temperature": 40, "humidity": 90})
        second = client.post("/api/costs/estimate", json=scenario_payload(room["id"], cooling_capacity_btu_h=24000)).json()["results"]
        assert first == second


def test_label_method_requires_reference_and_applies_explicit_linear_ratio():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        payload = scenario_payload(room["id"], method="label", average_power_kw=None,
            label_energy_kwh="500", label_reference_hours="2000", label_period="year")
        response = client.post("/api/costs/estimate", json=payload)
        assert response.status_code == 200
        result = response.json()["results"]
        assert result["monthly_energy_kwh"] == "44.0000" and result["monthly_cost"] == "39.60"
        assert any("aproximação linear" in item for item in result["limitations"])
        for field in ["label_reference_hours", "label_energy_kwh", "label_period"]:
            assert client.post("/api/costs/estimate", json={**payload, field: None}).status_code == 422
        assert client.post("/api/costs/estimate", json={**payload, "parameter_source": ""}).status_code == 422
        assert client.post("/api/costs/estimate", json={**payload, "label_period": "month", "label_reference_hours": 800}).status_code == 422


def test_decimal_rounding_and_explicit_zero_usage():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        payload = scenario_payload(room["id"], average_power_kw="0.3333", hours_per_day="1", days_per_month=1, tariff_per_kwh="0.1")
        result = client.post("/api/costs/estimate", json=payload).json()["results"]
        assert result["monthly_cost"] == "0.03"
        assert result["annual_cost"] == "0.40"  # Annual total uses unrounded monthly cost.
        result = client.post("/api/costs/estimate", json={**payload, "hours_per_day": "0"}).json()["results"]
        assert result["monthly_cost"] == "0.00" and result["annual_cost"] == "0.00"
        assert result["series"][36]["total_cost"] == "3000.00"


def test_cost_scenario_crud_isolated_by_room_and_deletion_keeps_readings():
    with authenticated_client() as client:
        room1, room2 = client.get("/api/rooms").json()
        client.post("/api/readings", json=sample_payload(room1["device_id"]))
        response = client.post("/api/costs/scenarios", json=scenario_payload(room1["id"]))
        assert response.status_code == 201
        scenario = response.json()
        assert client.get(f"/api/costs/scenarios/{scenario['id']}").json()["results"] == scenario["results"]
        assert client.get("/api/costs/scenarios", params={"room_id": room2["id"]}).json() == []
        assert len(client.get("/api/costs/scenarios", params={"room_id": room1["id"]}).json()) == 1
        updated = client.put(f"/api/costs/scenarios/{scenario['id']}", json=scenario_payload(room1["id"], hours_per_day="4"))
        assert updated.status_code == 200 and updated.json()["results"]["monthly_cost"] == "95.04"
        assert client.put(f"/api/costs/scenarios/{scenario['id']}", json=scenario_payload(room2["id"])).status_code == 422
        assert client.delete(f"/api/costs/scenarios/{scenario['id']}").status_code == 400
        assert client.delete(f"/api/costs/scenarios/{scenario['id']}?confirm=true").status_code == 204
        assert client.get(f"/api/costs/scenarios/{scenario['id']}").status_code == 404
        assert client.get("/api/readings/summary").json()["total_readings"] == 1


def test_comparison_and_export_include_parameters_formulas_limits_and_36_months():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        a = client.post("/api/costs/scenarios", json=scenario_payload(room["id"], name="=TESTE", notes="+Nota de teste")).json()
        b = client.post("/api/costs/scenarios", json=scenario_payload(room["id"], name="Alternativa B", hours_per_day="4")).json()
        payload = {"scenario_ids": [a["id"], b["id"]], "months": 36}
        comparison = client.post("/api/costs/compare", json=payload)
        assert comparison.status_code == 200
        assert Decimal(comparison.json()["difference_b_minus_a"]["total_cost"]) == Decimal("-3421.44")
        assert client.post("/api/costs/compare", json={**payload, "months": 18}).status_code == 422
        assert client.post("/api/costs/compare", json={**payload, "scenario_ids": [a["id"], a["id"]]}).status_code == 422
        report = client.get("/api/costs/report", params=[("scenario_id", a["id"]), ("scenario_id", b["id"]), ("months", 36)])
        assert report.status_code == 200 and "attachment" in report.headers["content-disposition"]
        for text in ["estimativas", "BTU/h", "kW", "Fórmula", "Limitação", "1.1", "9842.88", "Manutenção só é incluída quando informada", "'=TESTE", "'+Nota de teste"]:
            assert text in report.text
        assert client.get("/api/costs/report", params={"scenario_id": a["id"], "months": 18}).status_code == 422


def test_cost_validation_and_archived_room_access():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        payload = scenario_payload(room["id"])
        for field, value in [("average_power_kw", None), ("tariff_per_kwh", "-1"), ("equipment_price", "-1"),
            ("installation_cost", None), ("hours_per_day", "25"), ("days_per_month", 32),
            ("cooling_capacity_btu_h", True), ("days_per_month", True), ("tariff_per_kwh", "NaN"),
            ("name", "   "), ("equipment_price", "1.234")]:
            assert client.post("/api/costs/estimate", json={**payload, field: value}).status_code == 422, (field, value)
        scenario = client.post("/api/costs/scenarios", json=payload).json()
        client.delete(f"/api/rooms/{room['id']}?confirm=true")
        assert client.get(f"/api/costs/scenarios/{scenario['id']}").status_code == 404
        assert client.post("/api/costs/estimate", json=payload).status_code == 404


def test_maintenance_schedule_is_optional_and_charged_only_at_interval_boundaries():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        payload = scenario_payload(room["id"], maintenance_cost="180.25", maintenance_interval_months=6)
        result = client.post("/api/costs/estimate", json=payload).json()["results"]
        assert result["maintenance_informed"] is True
        assert result["monthly_cost"] == "190.08"  # Energy cost keeps its existing meaning.
        assert result["annual_maintenance_cost"] == "360.50"
        assert result["annual_operating_cost"] == "2641.46"
        assert result["series"][0]["maintenance_cost"] == "0.00"
        assert result["series"][5]["maintenance_cost"] == "0.00"
        assert result["series"][6]["maintenance_cost"] == "180.25"
        assert result["series"][7]["maintenance_cost"] == "0.00"
        assert result["series"][36]["cumulative_maintenance_cost"] == "1081.50"
        assert result["projections"][2]["total_cost"] == "10924.38"
        # A schedule longer than the projection incurs no event yet, but is still informed.
        later = client.post("/api/costs/estimate", json={**payload, "maintenance_interval_months": 48}).json()["results"]
        assert later["maintenance_informed"] and later["annual_maintenance_cost"] == "0.00"
        missing = client.post("/api/costs/estimate", json=scenario_payload(room["id"])).json()["results"]
        assert missing["maintenance_informed"] is False
        assert missing["annual_maintenance_cost"] is None
        assert missing["projections"][0]["maintenance_cost"] is None
        zero = client.post("/api/costs/estimate", json={**payload, "maintenance_cost": "0"}).json()["results"]
        assert zero["maintenance_informed"] and zero["annual_maintenance_cost"] == "0.00"


def test_maintenance_validation_persistence_and_legacy_client_edit():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        payload = scenario_payload(room["id"], maintenance_cost="150.00", maintenance_interval_months=12)
        for changes in [{"maintenance_cost": None}, {"maintenance_interval_months": None},
                        {"maintenance_cost": "-1"}, {"maintenance_cost": "1.234"},
                        {"maintenance_interval_months": 0}, {"maintenance_interval_months": 121},
                        {"maintenance_interval_months": True}, {"maintenance_interval_months": 1.5}]:
            assert client.post("/api/costs/estimate", json={**payload, **changes}).status_code == 422
        saved = client.post("/api/costs/scenarios", json=payload).json()
        url = f"/api/costs/scenarios/{saved['id']}"
        edited = client.put(url, json=scenario_payload(room["id"], name="Edição por cliente anterior")).json()
        assert edited["parameters"]["maintenance_cost"] == "150.00"
        assert edited["parameters"]["maintenance_interval_months"] == 12
        assert client.get(url).json()["results"]["annual_maintenance_cost"] == "150.00"
        removed = client.put(url, json={**payload, "maintenance_cost": None, "maintenance_interval_months": None}).json()
        assert removed["results"]["maintenance_informed"] is False


def test_comparison_uses_common_tariff_without_changing_saved_scenarios():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        a = client.post("/api/costs/scenarios", json=scenario_payload(room["id"])).json()
        b = client.post("/api/costs/scenarios", json=scenario_payload(room["id"], tariff_per_kwh="1.8", maintenance_cost="100", maintenance_interval_months=12)).json()
        payload = {"scenario_ids": [a["id"], b["id"]], "months": 24}
        shared = client.post("/api/costs/compare", json=payload).json()
        assert Decimal(shared["comparison_basis"]["common_tariff_per_kwh"]) == Decimal("0.9")
        assert shared["difference_b_minus_a"]["monthly_cost"] == "0.00"
        assert shared["difference_b_minus_a"]["total_cost"] == "200.00"
        assert shared["lowest_total_cost_scenario_id"] == a["id"] and not shared["is_tie"]
        individual = client.post("/api/costs/compare", json={**payload, "tariff_mode": "scenario"}).json()
        assert individual["difference_b_minus_a"]["monthly_cost"] == "190.08"
        zero = client.post("/api/costs/compare", json={**payload, "common_tariff_per_kwh": "0"}).json()
        assert zero["scenarios"][1]["results"]["monthly_cost"] == "0.00"
        assert client.get(f"/api/costs/scenarios/{b['id']}").json() == b
        assert client.post("/api/costs/compare", json={**payload, "tariff_mode": "scenario", "common_tariff_per_kwh": "1"}).status_code == 422
        tie = client.post("/api/costs/compare", json={**payload, "scenario_ids": [b["id"], a["id"]], "common_tariff_per_kwh": "0.5"}).json()
        assert tie["lowest_total_cost_scenario_id"] == a["id"]  # Winner is independent of selection order.
        report = client.get("/api/costs/report", params=[("scenario_id", a["id"]), ("scenario_id", b["id"]), ("months", 24)])
        assert "Tarifa original salva" in report.text and "Manutenção acumulada" in report.text
        assert "200.00" in report.text and "Manutenção anual prevista" in report.text
        assert client.get("/api/costs/report", params=[("scenario_id", a["id"]), ("scenario_id", b["id"]), ("common_tariff_per_kwh", "-1")]).status_code == 422


def test_equal_totals_do_not_claim_unique_winner_and_maintenance_uses_exact_values():
    from app.schemas.cost_schema import CostScenarioInput
    from app.services.cost_service import calculate_costs

    result = calculate_costs(CostScenarioInput(**scenario_payload("room", average_power_kw="0.3333",
        hours_per_day="1", days_per_month=1, tariff_per_kwh="0.1", maintenance_cost="0.01", maintenance_interval_months=1)))
    assert result["projections"][0]["total_cost"] == Decimal("3000.52")
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        ids = [client.post("/api/costs/scenarios", json=scenario_payload(room["id"])).json()["id"] for _ in range(2)]
        comparison = client.post("/api/costs/compare", json={"scenario_ids": ids}).json()
        assert comparison["is_tie"] and comparison["lowest_total_cost_scenario_id"] is None


def test_maintenance_migration_preserves_existing_scenarios_and_is_idempotent(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from app.services import storage_service

    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy_costs.db'}")
    monkeypatch.setattr(storage_service, "engine", legacy)
    storage_service.initialize_storage()
    with legacy.begin() as connection:
        room_id = connection.scalar(text("SELECT id FROM rooms LIMIT 1"))
        connection.execute(text("""INSERT INTO cost_scenarios (
            id, room_id, name, equipment_model, cooling_capacity_btu_h, method,
            average_power_kw, equipment_price, installation_cost, hours_per_day,
            days_per_month, tariff_per_kwh, parameter_source, notes
        ) VALUES ('original-cost', :room_id, 'Original', 'Modelo original', 12000,
            'power', 1.2, 2400, 600, 8, 22, 0.9, 'Fonte original', 'Nota original')"""), {"room_id": room_id})
        connection.execute(text("ALTER TABLE cost_scenarios DROP COLUMN maintenance_cost"))
        connection.execute(text("ALTER TABLE cost_scenarios DROP COLUMN maintenance_interval_months"))
        connection.execute(text("DELETE FROM schema_migrations WHERE version='cost_maintenance_v1'"))
        before = dict(connection.execute(text("SELECT * FROM cost_scenarios")).mappings().one())
    storage_service.initialize_storage()  # Must run even when rooms_v1 already exists.
    storage_service.initialize_storage()
    with legacy.connect() as connection:
        after = dict(connection.execute(text("SELECT * FROM cost_scenarios")).mappings().one())
        assert after.pop("maintenance_cost") is None
        assert after.pop("maintenance_interval_months") is None
        assert after == before
        assert connection.scalar(text("SELECT count(*) FROM schema_migrations WHERE version='cost_maintenance_v1'")) == 1
    legacy.dispose()


def test_environmental_context_separates_counts_and_does_not_bridge_gaps_or_invalid_data():
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.sensor_reading import SensorReading

    with authenticated_client() as client:
        room, other = client.get("/api/rooms").json()
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        with Session(engine) as db:
            # [0,10] outside; [10,20] normal; invalid sample breaks [20,25].
            for minute, temperature, status, source in [(0, 30, "alerta", "sensor"), (10, 23, "ideal", "sensor"),
                (20, 30, "critico", "sensor"), (21, 100, "critico", "sensor"),
                (25, 30, "critico", "sensor"), (90, 23, "ideal", "sensor"),
                (100, 23, "ideal", "external_api"), (105, 23, "ideal", "sensor")]:
                db.add(SensorReading(**{**sample_payload(room["device_id"]), "room_id": room["id"],
                    "temperature": temperature, "air_quality_status": status, "data_source": source,
                    "created_at": start + timedelta(minutes=minute)}))
            db.commit()
        c = client.get("/api/costs/context", params={"room_id": room["id"], "days": 1}).json()
        assert c["count"] == 6 and c["excluded_count"] == 2
        assert c["alerts"] == 1 and c["critical"] == 2
        assert c["outside_seconds"] == 600 and c["covered_seconds"] == 1200
        assert 1 < c["coverage_percent"] < 2
        empty = client.get("/api/costs/context", params={"room_id": other["id"]}).json()
        assert empty["count"] == 0 and empty["outside_seconds"] is None
        assert empty["temperature_avg"] is None and empty["coverage_percent"] == 0
        assert client.get("/api/costs/context", params={"room_id": room["id"], "days": 0}).status_code == 422


def test_printable_report_has_graphs_context_analysis_and_escapes_user_text():
    with authenticated_client() as client:
        room = client.get("/api/rooms").json()[0]
        client.post("/api/readings", json=sample_payload(room["device_id"]))
        a = client.post("/api/costs/scenarios", json=scenario_payload(room["id"], name='<script>alert("x")</script>')).json()
        b = client.post("/api/costs/scenarios", json=scenario_payload(room["id"], hours_per_day="4")).json()
        params = [("scenario_id", a["id"]), ("scenario_id", b["id"]), ("months", 36), ("days", 7)]
        response = client.get("/api/costs/report/print", params=params)
        assert response.status_code == 200, response.text
        for text in ["<svg", "<polyline", "Análise do Investimento", "Indicadores ambientais", "9.842", "1.1", "Manutenção", "&lt;script&gt;"]:
            assert text in response.text
        assert '<script>alert("x")</script>' not in response.text
        assert client.get("/api/costs/report/print", params={"scenario_id": a["id"], "months": 18}).status_code == 422
        portfolio = client.get("/api/costs/portfolio").json()
        assert len(portfolio) == 2 and sum(len(r["scenarios"]) for r in portfolio) == 2
        client.delete(f"/api/rooms/{room['id']}?confirm=true")
        assert client.get("/api/costs/report/print", params=params).status_code == 404
        assert len(client.get("/api/costs/portfolio").json()) == 1
