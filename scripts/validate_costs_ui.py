"""Browser acceptance tests for the isolated test server on port 8001."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    evidence = Path("docs/evidence")
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"server": "http://127.0.0.1:8001", "data": "Valores exclusivos de testes em base isolada", "checks": [], "errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="pt-BR", timezone_id="America/Sao_Paulo")
        page = context.new_page()
        page.on("pageerror", lambda error: report["errors"].append(str(error)))
        page.goto("http://127.0.0.1:8001/login")
        page.locator("#username").fill("ui-check"); page.locator("#password").fill("ui-validation-only"); page.locator("#loginButton").click()
        expect(page.locator("#roomCards .room-card")).to_have_count(2)
        rooms = context.request.get("http://127.0.0.1:8001/api/rooms").json()
        for room in rooms:
            response = context.request.post("http://127.0.0.1:8001/api/readings", data={
                "device_id": room["device_id"], "location": "Contexto exclusivo do teste", "temperature": 23.5,
                "humidity": 48.2, "co2": 750, "pm25": 8.5, "pressure": 1013, "pm10": 18,
            })
            assert response.status == 201
        page.locator('[data-view="costsView"]').click()
        expect(page.locator("#costsView")).to_be_visible()
        expect(page.locator("#costClimateContext")).to_contain_text("Sala 1")
        expect(page.locator("#costClimateContext")).to_contain_text("23,5")
        assert page.locator("#costPrice").input_value() == ""
        assert page.locator("#costTariff").input_value() == ""
        assert page.locator(".nav-menu .nav-item").last.get_attribute("data-view") == "roomsView"

        def fill(name, method="power"):
            page.locator("#newCostScenario").click()
            for suffix, value in {"Name": name, "Model": "Modelo exclusivo de teste", "Capacity": "12000",
                "Price": "2400", "Installation": "600", "Hours": "8", "Days": "22", "Tariff": "0.9"}.items():
                page.locator(f"#cost{suffix}").fill(value)
            page.locator("#costMethod").select_option(method)
            if method == "power":
                page.locator("#costPower").fill("1.2")
            else:
                page.locator("#costLabelEnergy").fill("500")
                page.locator("#costLabelHours").fill("2000")
                page.locator("#costLabelPeriod").select_option("year")
            page.locator("#costSource").fill("Valores apenas para teste automatizado; não são orçamento ou etiqueta reais")

        fill("Teste A - potência média")
        page.locator("#calculateCost").click()
        expect(page.locator("#costResultMetrics")).to_contain_text("190,08")
        assert context.request.get("http://127.0.0.1:8001/api/costs/scenarios", params={"room_id": rooms[0]["id"]}).json() == []
        page.locator("#saveCostScenario").click()
        expect(page.locator("#costScenarioTable [data-cost-edit]")).to_have_count(1)
        fill("Teste B - referência de etiqueta", "label")
        page.locator("#saveCostScenario").click()
        expect(page.locator("#costScenarioTable [data-cost-edit]")).to_have_count(2)
        expect(page.locator("#costResultMetrics")).to_contain_text("39,60")
        expect(page.locator("#compareCosts")).to_be_enabled()
        page.locator("#compareCosts").click()
        expect(page.locator("#costComparisonContext")).to_contain_text("Diferença B")
        for months in ["24", "36", "12", "36"]:
            page.locator("#costHorizon").select_option(months)
            expect(page.locator("#costChartTitle")).to_contain_text(f"{months} meses")
            expect(page.locator("#costTimelineTable tr")).to_have_count(int(months) + 1)
        expect(page.locator("#costComparisonContext")).to_contain_text("5.417,28")
        page.locator("#costCumulativeChart").focus(); page.keyboard.press("ArrowLeft")
        expect(page.locator("#costCumulativeChartTooltip")).to_contain_text("Mês 35")
        with page.expect_download() as downloaded:
            page.locator("#exportCostSelection").click()
        downloaded.value.save_as(".venv/costs-ui-report.csv")
        text = Path(".venv/costs-ui-report.csv").read_text(encoding="utf-8-sig")
        for expected in ["Teste A", "Teste B", "Fórmula", "Limitação", "BTU/h", "9842.88", "4425.60"]:
            assert expected in text, expected
        page.locator(".content-shell").evaluate("element => element.scrollTop = 0")
        page.screenshot(path=str(evidence / "costs-desktop.png"), full_page=True)
        page.locator("#costChartsPanel").screenshot(path=str(evidence / "costs-comparison.png"))
        report["checks"].append("Sala 1: blank initial prices; power and label methods; preview; persistence; comparison at 12/24/36 months; keyboard charts and CSV")

        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".content-shell").evaluate("element => element.scrollTop = 0")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(evidence / "costs-mobile.png"), full_page=True)
        report["checks"].append("Responsive module at 390px without horizontal page overflow")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator("#roomSelect").select_option(rooms[1]["device_id"])
        expect(page.locator("#costsView")).to_be_visible()
        expect(page.locator("#costClimateContext")).to_contain_text("Sala 2")
        expect(page.locator("#costScenarioTable")).to_contain_text("Nenhum cenário salvo")
        assert page.locator("#costName").input_value() == ""
        fill("Teste C - Sala 2")
        page.locator("#saveCostScenario").click()
        expect(page.locator("#costScenarioTable [data-cost-edit]")).to_have_count(1)
        page.locator('[data-action="cost-room-details"]').click()
        expect(page.locator("#generalView")).to_be_visible()
        expect(page.locator("#roomName")).to_have_text("Sala 2")
        page.locator('[data-action="room-costs"]').click()
        expect(page.locator("#costScenarioTable")).to_contain_text("Teste C")
        report["checks"].append("Sala 2: room selection stays in module; independent saved scenario; links to and from individual dashboard")

        page.locator("#roomSelect").select_option(rooms[0]["device_id"])
        expect(page.locator("#costScenarioTable [data-cost-edit]")).to_have_count(2)
        first = page.locator("#costScenarioTable tr").filter(has_text="Teste A")
        first.locator("[data-cost-edit]").click()
        page.locator("#costHours").fill("4")
        page.locator("#saveCostScenario").click()
        expect(page.locator("#costResultMetrics")).to_contain_text("95,04")
        second = page.locator("#costScenarioTable tr").filter(has_text="Teste B")
        page.once("dialog", lambda dialog: dialog.dismiss())
        second.locator("[data-cost-delete]").click()
        expect(page.locator("#costScenarioTable [data-cost-edit]")).to_have_count(2)
        page.once("dialog", lambda dialog: dialog.accept())
        second.locator("[data-cost-delete]").click()
        expect(page.locator("#costScenarioTable [data-cost-edit]")).to_have_count(1)
        page.reload(); expect(page.locator("#roomCards .room-card")).to_have_count(2)
        page.locator('[data-view="costsView"]').click()
        expect(page.locator("#costScenarioTable")).to_contain_text("Teste A")
        assert context.request.get("http://127.0.0.1:8001/api/readings/summary").json()["total_readings"] == 2
        assert len(context.request.get("http://127.0.0.1:8001/api/costs/scenarios", params={"room_id": rooms[1]["id"]}).json()) == 1
        report["checks"].append("Edit, cancel/confirm deletion, persistence across reload and preservation of rooms and readings")
        # Evolution: live preview, maintenance, common tariffs, portfolio and rich report.
        first = page.locator("#costScenarioTable tr").filter(has_text="Teste A")
        first.locator("[data-cost-edit]").click()
        page.locator("#costMaintenance").fill("120")
        page.locator("#costMaintenanceInterval").fill("6")
        expect(page.locator("#costResultMetrics")).to_contain_text("240,00")
        expect(page.locator("#costNotice")).to_contain_text("automaticamente")
        page.locator("#saveCostScenario").click()
        expect(page.locator("#costNotice")).to_contain_text("Cenário salvo")
        page.locator("#costHours").fill("8")
        expect(page.locator("#costResultMetrics")).to_contain_text("190,08")
        expect(page.locator("#costNotice")).to_contain_text("automaticamente")
        saved = context.request.get("http://127.0.0.1:8001/api/costs/scenarios", params={"room_id": rooms[0]["id"]}).json()[0]
        assert saved["parameters"]["hours_per_day"] == "4.00"  # Preview never saves silently.
        page.locator("#saveCostScenario").click()
        expect(page.locator("#costNotice")).to_contain_text("Cenário salvo")
        params = {**saved["parameters"], "name": "Teste D - tarifa diferente", "tariff_per_kwh": "1.8", "hours_per_day": "8", "maintenance_cost": None, "maintenance_interval_months": None}
        alternate = context.request.post("http://127.0.0.1:8001/api/costs/scenarios", data=params).json()
        page.evaluate("refreshCostsView()")
        expect(page.locator("#costScenarioTable [data-cost-select]")).to_have_count(2)
        page.locator(f'[data-cost-select="{saved["id"]}"]').check()
        page.locator(f'[data-cost-select="{alternate["id"]}"]').check()
        page.locator("#compareCosts").click()
        expect(page.locator("#costWinner")).to_contain_text("Teste D")
        expect(page.locator("#costCompareTable")).to_contain_text("120,00")
        expect(page.locator("#costComparisonContext")).to_contain_text("Tarifa comum")
        page.locator("#costTariffMode").select_option("scenario")
        expect(page.locator("#costWinner")).to_contain_text("Teste A")
        page.locator("#costTariffMode").select_option("shared")
        expect(page.locator("#costWinner")).to_contain_text("Teste D")
        page.locator(f'[data-cost-portfolio="{rooms[0]["id"]}"]').select_option(saved["id"])
        c = context.request.get("http://127.0.0.1:8001/api/costs/scenarios", params={"room_id": rooms[1]["id"]}).json()[0]
        page.locator(f'[data-cost-portfolio="{rooms[1]["id"]}"]').select_option(c["id"])
        expect(page.locator(".cost-room-bar")).to_have_count(2)
        page.locator("#costClimateDays").select_option("1")
        expect(page.locator("#costClimateMetrics")).to_contain_text("Não calculável")  # Single reading provides no duration.
        expect(page.locator("#costAnalysis")).to_contain_text("diferença")
        with page.expect_popup() as opened:
            page.locator("#printCostReport").click()
        printed = opened.value
        expect(printed.locator("h1")).to_contain_text("Custos e Investimentos")
        expect(printed.locator("svg polyline")).to_have_count(2)
        expect(printed.locator("body")).to_contain_text("Análise do Investimento")
        printed.pdf(path=".venv/costs-evolution-report.pdf", format="A4")
        printed.close()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#costResults").screenshot(path=str(evidence / "costs-evolution-mobile.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator("#costResults").screenshot(path=str(evidence / "costs-evolution-summary.png"))
        report["checks"].append("Evolution: automatic preview without autosave; maintenance; common/individual tariffs and winner; one scenario per room; no invented duration; printable graph report and PDF; responsive results")
        assert not report["errors"], report["errors"]
        report["result"] = "passed"
        (evidence / "costs-ui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
