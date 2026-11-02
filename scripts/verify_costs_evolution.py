"""Read-only deployment checks. Run inside the app container before/after restart."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database import engine
from app.security.auth import create_access_token, get_configured_credentials

BASELINE = Path("backups/costs_evolution_before.json")


def fingerprints():
    result = {}
    with engine.connect() as connection:
        for table in ("sensor_readings", "rooms", "cost_scenarios"):
            # Added nullable fields are excluded only from the legacy scenario fingerprint.
            expression = "to_jsonb(t)"
            if table == "cost_scenarios":
                expression += " - 'maintenance_cost' - 'maintenance_interval_months'"
            count, digest = connection.execute(text(
                f"SELECT count(*), md5(coalesce(string_agg(md5(({expression})::text), '' ORDER BY id), '')) FROM {table} t"
            )).one()
            result[table] = {"count": count, "sha_fingerprint": digest}
    return result


def main():
    mode = sys.argv[1]
    snapshot = fingerprints()
    if mode == "before":
        BASELINE.parent.mkdir(exist_ok=True)
        BASELINE.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(json.dumps(snapshot))
        return
    assert mode == "after"
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert snapshot == baseline, {"before": baseline, "after": snapshot}
    username, _ = get_configured_credentials()
    token = create_access_token(username)

    def get(path, html=False):
        with urlopen(Request("http://127.0.0.1:8000" + path, headers={"Authorization": "Bearer " + token}), timeout=30) as response:
            body = response.read().decode("utf-8")
            return body if html else json.loads(body)

    checks = []
    for path in ("/health", "/api/readings/history", "/api/readings/alerts", "/api/rooms/overview", "/api/costs/portfolio"):
        get(path); checks.append(path)
    for room in get("/api/rooms"):
        context = get(f"/api/costs/context?room_id={room['id']}&days=7")
        assert "outside_seconds" in context and "coverage_percent" in context
        scenarios = get(f"/api/costs/scenarios?room_id={room['id']}")
        for scenario in scenarios:
            assert "maintenance_informed" in scenario["results"]
        checks.append("context and scenarios: " + room["id"])
    html = get("/", html=True)
    assert all(value in html for value in ("costMaintenance", "costClimateDays", "printCostReport", "costAnalysis"))
    report = {"result": "passed", "preserved": snapshot, "checks": checks, "financial_test_data_inserted": False}
    Path("docs/evidence/costs-evolution-deployment.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
