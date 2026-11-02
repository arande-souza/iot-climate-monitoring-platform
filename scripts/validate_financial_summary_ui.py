"""Read-only browser check against the running local app and its saved scenarios."""
import json
import subprocess
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    # Capture a short-lived token internally; never print credentials or the token.
    token = subprocess.check_output(["docker", "compose", "exec", "-T", "app", "python", "-c",
        "from app.security.auth import create_access_token, get_configured_credentials; print(create_access_token(get_configured_credentials()[0]))"], text=True).strip()
    report = {"result": "passed", "checks": [], "errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="pt-BR")
        context.add_cookies([{"name": "access_token", "value": token, "domain": "127.0.0.1", "path": "/", "httpOnly": True, "sameSite": "Lax"}])
        context.add_init_script("localStorage.setItem('accessToken', " + json.dumps(token) + ");")
        page = context.new_page()
        page.on("pageerror", lambda e: report["errors"].append(str(e)))
        page.goto("http://127.0.0.1:8000/")
        expect(page.locator("#roomCards .room-card")).to_have_count(2)
        rooms = context.request.get("http://127.0.0.1:8000/api/rooms").json()
        page.locator('[data-view="costsView"]').click()
        for room in rooms:
            page.locator("#roomSelect").select_option(room["device_id"])
            scenarios = context.request.get("http://127.0.0.1:8000/api/costs/scenarios", params={"room_id": room["id"]}).json()
            expect(page.locator("#costSummaryContext")).to_contain_text("10/2026")
            expect(page.locator("#costSummaryScenario option")).to_have_count(len(scenarios) + 1)
            assert page.locator("#costName").input_value() == ""  # Viewing a saved summary does not overwrite the form.
            # Changing selection must populate the four requested indicators with API results.
            scenario = min(scenarios, key=lambda s: s["parameters"]["name"])
            page.locator("#costSummaryScenario").select_option(scenario["id"])
            expect(page.locator("#costSummaryContext")).to_contain_text(scenario["parameters"]["name"])
            result = scenario["results"]
            for label, value in [("Investimento inicial", result["initial_investment"]),
                ("Custo mensal de energia", result["monthly_cost"]), ("Custo anual de energia", result["annual_cost"]),
                ("Total em 36 meses", result["projections"][2]["total_cost"])]:
                expected = page.evaluate("value => new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(Number(value))", value)
                card = page.locator("#costResultMetrics .summary-card").filter(has=page.locator("span", has_text=label))
                expect(card).to_contain_text(expected)
            page.locator("#newCostScenario").click()
            expect(page.locator("#costResults")).to_be_visible()
            expect(page.locator("#costResultMetrics")).to_contain_text("Preencha os parâmetros")
            page.evaluate("refreshCostsView()")
            expect(page.locator("#costResultMetrics")).to_contain_text("Preencha os parâmetros")
            page.locator("#costSummaryScenario").select_option(scenario["id"])
            report["checks"].append({"room": room["name"], "saved_scenarios": len(scenarios), "automatic_summary": True, "four_values_match_api": True})
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#costResults").screenshot(path="docs/evidence/financial-summary-mobile.png")
        assert not report["errors"], report["errors"]
        browser.close()
    Path("docs/evidence/financial-summary-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
