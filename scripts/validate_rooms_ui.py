"""Run against an isolated test server on port 8001, never against the live database."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    evidence = Path("docs/evidence")
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"server": "http://127.0.0.1:8001", "checks": [], "errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True,
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="pt-BR", timezone_id="America/Sao_Paulo")
        page = context.new_page()
        page.on("pageerror", lambda error: report["errors"].append(str(error)))
        page.goto("http://127.0.0.1:8001/login")
        page.locator("#username").fill("ui-check")
        page.locator("#password").fill("ui-validation-only")
        page.locator("#loginButton").click()
        expect(page.locator("#roomCards .room-card")).to_have_count(2)
        report["checks"].append("Login and preserved Sala 1 / Sala 2")

        now = datetime.now(timezone.utc)
        for device in ["esp32-sala-01", "esp32-sala-02"]:
            response = context.request.post("http://127.0.0.1:8001/simulator/generate", data={
                "device_id": device, "location": "Ambiente de validacao",
                "start_datetime": (now - timedelta(minutes=10)).isoformat(),
                "end_datetime": now.isoformat(), "frequency_seconds": 60, "profile": "normal",
            })
            assert response.status == 200, response.text()
        page.reload()
        expect(page.locator("#roomCards .room-card")).to_have_count(2)
        assert "Dados simulados" not in page.locator("body").inner_text()
        expect(page.locator("#overviewHistoryContext")).to_contain_text("Médias por sala")
        total = page.locator("#overviewSeriesTable tr").evaluate_all("rows => rows.reduce((total, row) => total + Number(row.cells[4].textContent), 0)")
        assert total == 22, total
        registered = context.request.get("http://127.0.0.1:8001/api/rooms").json()
        first_room_id = next(room["id"] for room in registered if room["device_id"] == "esp32-sala-01")
        with page.expect_response(lambda response: "/overview/history" in response.url and "room_id=" + first_room_id in response.url):
            page.locator("#overviewRoomFilter").select_option(first_room_id)
        expect(page.locator("#overviewHistoryContext")).to_contain_text("Médias por sala")
        page.locator("#overviewRoomFilter").select_option("")
        page.locator("#overviewPeriod").select_option("custom")
        page.locator("#overviewStart").fill("2020-01-01T00:00")
        page.locator("#overviewEnd").fill("2020-01-02T00:00")
        page.locator("#applyOverviewPeriod").click()
        expect(page.locator("#overviewHistoryContext")).to_contain_text("Nenhuma medição válida")
        page.locator("#overviewPeriod").select_option("1")
        expect(page.locator("#overviewHistoryContext")).to_contain_text("Médias por sala")
        report["checks"].append("Consolidated temperature, humidity and events: existing samples, room filter and empty custom period")

        for index in range(3, 11):
            page.locator('#overviewView [data-action="create-room"]').click()
            page.locator("#roomFormName").fill(f"Sala {index}")
            page.locator("#roomFormLocation").fill(f"Bloco {index}")
            page.locator("#roomFormIdentifier").fill(f"A-{index}")
            page.locator("#roomFormCity").fill("Santo André")
            page.locator("#roomFormState").fill("sp")
            page.locator("#roomFormInternalLocation").fill("Estoque")
            page.locator("#roomFormDescription").fill(f"Ambiente cadastrado pela interface: {index}")
            page.locator("#roomFormDevice").fill(f"esp32-ui-{index:02d}")
            page.locator("#saveRoomButton").click()
            expect(page.locator("#roomDialog")).not_to_be_visible()
            expect(page.locator("#roomCards .room-card")).to_have_count(index)
        report["checks"].append("Created Sala 3 through Sala 10 through the UI; automatic overview updates")
        room3 = page.locator("#roomCards .room-card").filter(has=page.get_by_role("heading", name="Sala 3", exact=True))
        room3.get_by_role("button", name="Configurar").click()
        page.locator("#roomFormName").fill("Laboratório editado")
        page.locator("#roomFormTempMax").fill("24")
        page.locator("#roomFormDevice").fill("esp32-ui-substituto")
        page.locator("#saveRoomButton").click()
        expect(page.locator("#roomDialog")).not_to_be_visible()
        expect(page.locator("#roomCards")).to_contain_text("Laboratório editado")
        expect(page.locator("#roomCards")).to_contain_text("Santo André / SP")
        expect(page.locator("#roomCards")).to_contain_text("Ambiente A-3 · Estoque")
        report["checks"].append("Edited name and room-specific threshold")
        page.locator(".content-shell").evaluate("element => element.scrollTop = 0")
        page.screenshot(path=str(evidence / "rooms-desktop.png"), full_page=True)
        page.locator(".overview-history").screenshot(path=str(evidence / "overview-consolidated.png"))

        page.locator("#roomCards .room-card").filter(has=page.get_by_role("heading", name="Sala 1", exact=True)).get_by_role("button", name="Ver ambiente →").click()
        expect(page.locator("#generalView")).to_be_visible()
        expect(page.locator("#roomHistoryContext")).to_contain_text("Gráficos mostram médias")
        assert "/rooms/" in page.url
        page.reload()
        expect(page.locator("#generalView")).to_be_visible()
        expect(page.locator("#roomHistoryContext")).to_contain_text("Gráficos mostram médias")
        # Time buckets aggregate multiple real samples; verify all 11 were counted.
        total_samples = page.locator("#roomSeriesTable tr").evaluate_all("rows => rows.reduce((total, row) => total + Number(row.cells[3].textContent), 0)")
        assert total_samples == 11, total_samples
        for period in ["7", "30", "1"]:
            with page.expect_response(lambda response: "/dashboard?days=" + period in response.url):
                page.locator("#detailPeriod").select_option(period)
        page.locator("#roomTemperatureChart").focus()
        page.keyboard.press("ArrowLeft")
        page.locator(".content-shell").evaluate("element => element.scrollTop = 0")
        page.screenshot(path=str(evidence / "room-detail.png"), full_page=True)
        assert page.locator("#pressure").inner_text() != "--"
        assert page.locator("#pm10").inner_text() != "--"
        report["checks"].append("Individual charts, 24h/7d/30d filters, accessible keyboard exploration and source labels")

        page.locator('[data-view="readingsView"]').click()
        expect(page.locator("#allReadingsTable tr")).to_have_count(11)
        page.locator("#readingsStatus").select_option("ideal")
        expect(page.locator("#allReadingsTable tr")).to_have_count(11)
        page.locator("#readingsPageSize").select_option("20")
        with page.expect_download() as download_info:
            page.locator("#exportReadingsReport").click()
        download = download_info.value
        download_path = Path(".venv/ui-readings-report.csv")
        download.save_as(str(download_path))
        content = download_path.read_text(encoding="utf-8-sig")
        assert "Pressao" in content and "PM10" in content and "Origem" in content
        page.locator('[data-view="alertsView"]').click()
        expect(page.locator("#alertsCount")).to_have_text("0 registros")
        with page.expect_download() as download_info:
            page.locator("#exportAlertsReport").click()
        download_info.value.save_as(".venv/ui-alerts-report.csv")
        report["checks"].append("Existing reading and alert history pages: filters, pagination, critical-hours chart and CSV downloads")

        page.locator('[data-view="comparisonView"]').click()
        expect(page.locator("#comparisonTable tr")).to_have_count(10)
        expect(page.locator("#comparisonTable")).to_contain_text("Laboratório editado")
        page.locator("#comparisonPeriod").select_option("7")
        expect(page.locator("#comparisonContext")).to_contain_text("Todas as salas")
        page.locator(".content-shell").evaluate("element => element.scrollTop = 0")
        page.screenshot(path=str(evidence / "rooms-comparison.png"), full_page=True)
        report["checks"].append("Comparison includes ten rooms; rooms without data remain explicitly empty")

        page.locator('[data-view="roomsView"]').click()
        card = page.locator("#roomManagement .room-card").filter(has=page.get_by_role("heading", name="Laboratório editado", exact=True))
        page.once("dialog", lambda dialog: dialog.dismiss())
        card.get_by_role("button", name="Excluir", exact=True).click()
        expect(page.locator("#roomManagement .room-card")).to_have_count(10)
        page.once("dialog", lambda dialog: dialog.accept())
        card.get_by_role("button", name="Excluir", exact=True).click()
        expect(page.locator("#roomManagement .room-card")).to_have_count(9)
        expect(page.locator("#roomManagement")).to_contain_text("Sala 1")
        expect(page.locator("#roomManagement")).to_contain_text("Sala 2")
        report["checks"].append("Deletion requires confirmation and preserves other rooms")

        page.set_viewport_size({"width": 390, "height": 844})
        page.locator('[data-view="overviewView"]').click()
        expect(page.locator("#roomCards .room-card")).to_have_count(9)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow on mobile"
        page.screenshot(path=str(evidence / "rooms-mobile.png"), full_page=True)
        page.locator("#roomCards .room-card").filter(has=page.get_by_role("heading", name="Sala 1", exact=True)).get_by_role("button", name="Ver ambiente →").click()
        expect(page.locator("#roomHistoryContext")).to_contain_text("Gráficos mostram médias")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Detail overflow on mobile"
        report["checks"].append("390px mobile overview and individual view without horizontal overflow")
        page.locator('[data-view="overviewView"]').click()
        expect(page.locator('#overviewView #updateSimulatedDataText')).to_have_text('Atualizar dados')
        expect(page.locator('#simulatorUpdateMessage')).to_have_text('Área de atualização manual')
        with page.expect_response(lambda response: '/simulator/update-all-until-now' in response.url) as updated:
            page.locator('#updateSimulatedData').click()
        result = updated.value.json()
        assert updated.value.status == 200 and result['total_rooms'] == 9
        assert result['updated_rooms'] >= 7
        expect(page.locator('#updateSimulatedData')).to_be_enabled(timeout=30000)
        registered = context.request.get('http://127.0.0.1:8001/api/rooms').json()
        for room in registered:
            summary = context.request.get('http://127.0.0.1:8001/api/readings/summary', params={'room_id': room['id']}).json()
            assert summary['total_readings'] > 0
        assert 'simulad' not in page.locator('body').inner_text().lower()
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('.content-shell').evaluate('element => element.scrollTop = 0')
        page.screenshot(path=str(evidence / 'manual-update-all-rooms.png'), full_page=True)
        report['checks'].append('Overview manual update generates readings for every active room with neutral labels')
        assert not report["errors"], report["errors"]
        report["result"] = "passed"
        (evidence / "rooms-ui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
