import csv
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cost_scenario import CostScenario
from app.models.room import Room
from app.schemas.cost_schema import CostComparisonInput, CostScenarioInput
from app.services.cost_service import calculate_costs
from app.services.room_service import get_room
from app.services.cost_analysis_service import environmental_context, investment_analysis, brl

router = APIRouter(prefix="/api/costs", tags=["costs and investments"])
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["brl"] = brl


@router.get("/context")
def climate_context(room_id: str, days: int = Query(7, ge=1, le=366), db: Session = Depends(get_db)):
    return environmental_context(db, get_room(db, room_id), days)


@router.get("/portfolio")
def portfolio(db: Session = Depends(get_db)):
    rooms = db.scalars(select(Room).where(Room.is_deleted.is_(False)).order_by(Room.name, Room.id)).all()
    return [{"room_id": room.id, "room_name": room.name,
        "scenarios": list_scenarios(room.id, db)} for room in rooms]


def get_scenario(db, scenario_id):
    scenario = db.get(CostScenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "Cenário não encontrado")
    get_room(db, scenario.room_id)
    return scenario


def scenario_result(db, scenario):
    payload = CostScenarioInput.model_validate(scenario)
    room = get_room(db, scenario.room_id)
    return {"id": scenario.id, "room_name": room.name,
            "parameters": payload.model_dump(mode="json"),
            "results": jsonable_encoder(calculate_costs(payload), custom_encoder={Decimal: str}),
            "created_at": scenario.created_at, "updated_at": scenario.updated_at}


@router.get("/scenarios")
def list_scenarios(room_id: str, db: Session = Depends(get_db)):
    get_room(db, room_id)
    rows = db.scalars(select(CostScenario).where(CostScenario.room_id == room_id).order_by(CostScenario.created_at, CostScenario.id)).all()
    return [scenario_result(db, row) for row in rows]


@router.post("/estimate")
def estimate(payload: CostScenarioInput, db: Session = Depends(get_db)):
    room = get_room(db, payload.room_id)
    return {"id": None, "room_name": room.name, "parameters": payload.model_dump(mode="json"),
            "results": jsonable_encoder(calculate_costs(payload), custom_encoder={Decimal: str})}


@router.post("/scenarios", status_code=201)
def create_scenario(payload: CostScenarioInput, db: Session = Depends(get_db)):
    get_room(db, payload.room_id)
    scenario = CostScenario(**payload.model_dump())
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario_result(db, scenario)


@router.get("/scenarios/{scenario_id}")
def read_scenario(scenario_id: str, db: Session = Depends(get_db)):
    return scenario_result(db, get_scenario(db, scenario_id))


@router.put("/scenarios/{scenario_id}")
def edit_scenario(scenario_id: str, payload: CostScenarioInput, db: Session = Depends(get_db)):
    scenario = get_scenario(db, scenario_id)
    if scenario.room_id != payload.room_id:
        raise HTTPException(422, "O cenário deve permanecer vinculado à sala original")
    values = payload.model_dump()
    # Older clients do not send maintenance fields; keep the saved schedule on edit.
    maintenance_fields = {"maintenance_cost", "maintenance_interval_months"}
    if not maintenance_fields.intersection(payload.model_fields_set):
        for key in maintenance_fields:
            values[key] = getattr(scenario, key)
    for key, value in values.items():
        setattr(scenario, key, value)
    db.commit()
    db.refresh(scenario)
    return scenario_result(db, scenario)


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, confirm: bool = False, db: Session = Depends(get_db)):
    scenario = get_scenario(db, scenario_id)
    if not confirm:
        raise HTTPException(400, "Confirme a exclusão com confirm=true")
    db.delete(scenario)
    db.commit()
    return Response(status_code=204)


def comparison_result(payload: CostComparisonInput, db: Session):
    scenarios = [scenario_result(db, get_scenario(db, scenario_id)) for scenario_id in payload.scenario_ids]
    original_tariffs = [item["parameters"]["tariff_per_kwh"] for item in scenarios]
    common_tariff = None
    if payload.tariff_mode == "shared":
        common_tariff = payload.common_tariff_per_kwh
        if common_tariff is None:
            common_tariff = Decimal(original_tariffs[0])
        for scenario in scenarios:
            scenario["original_parameters"] = scenario["parameters"].copy()
            parameters = CostScenarioInput.model_validate({**scenario["parameters"], "tariff_per_kwh": common_tariff})
            scenario["parameters"] = parameters.model_dump(mode="json")
            scenario["results"] = jsonable_encoder(calculate_costs(parameters), custom_encoder={Decimal: str})
    a, b = [item["results"] for item in scenarios]
    totals = [Decimal(item["series"][payload.months]["total_cost"]) for item in (a, b)]
    return {"months": payload.months, "scenarios": scenarios,
            "comparison_basis": {"tariff_mode": payload.tariff_mode,
                "common_tariff_per_kwh": str(common_tariff) if common_tariff is not None else None,
                "original_tariffs_per_kwh": original_tariffs,
                "note": "Tarifa comum aplicada somente à comparação; cenários salvos preservados." if common_tariff is not None else "Tarifas individuais explicitamente selecionadas; as premissas podem ser diferentes."},
            "lowest_total_cost_scenario_id": None if totals[0] == totals[1] else scenarios[0 if totals[0] < totals[1] else 1]["id"],
            "is_tie": totals[0] == totals[1],
            "interpretation": "Menor custo projetado não significa melhor capacidade de climatização, economia real ou retorno do investimento.",
            "difference_b_minus_a": {
                "monthly_cost": str(Decimal(b["monthly_cost"]) - Decimal(a["monthly_cost"])),
                "initial_investment": str(Decimal(b["initial_investment"]) - Decimal(a["initial_investment"])),
                "total_cost": str(Decimal(b["series"][payload.months]["total_cost"]) - Decimal(a["series"][payload.months]["total_cost"])),
            }}


@router.post("/compare")
def compare(payload: CostComparisonInput, db: Session = Depends(get_db)):
    return comparison_result(payload, db)


@router.get("/report/print")
def printable_report(request: Request, scenario_id: list[str] = Query(..., min_length=1, max_length=2),
    months: int = 12, days: int = Query(7, ge=1, le=366),
    tariff_mode: Literal["shared", "scenario"] = "shared",
    common_tariff_per_kwh: Decimal | None = Query(None, ge=0, le=1000, max_digits=12, decimal_places=6),
    db: Session = Depends(get_db)):
    if months not in (12, 24, 36) or len(set(scenario_id)) != len(scenario_id) or (tariff_mode == "scenario" and common_tariff_per_kwh is not None):
        raise HTTPException(422, "Selecione cenários distintos e uma base de tarifa válida")
    comparison = None
    if len(scenario_id) == 2:
        comparison = comparison_result(CostComparisonInput(scenario_ids=scenario_id, months=months,
            tariff_mode=tariff_mode, common_tariff_per_kwh=common_tariff_per_kwh), db)
        scenarios = comparison["scenarios"]
    else:
        if common_tariff_per_kwh is not None:
            raise HTTPException(422, "Tarifa comum exige dois cenários")
        scenarios = [scenario_result(db, get_scenario(db, scenario_id[0]))]
    contexts = {s["parameters"]["room_id"]: environmental_context(db, get_room(db, s["parameters"]["room_id"]), days) for s in scenarios}
    analyses = [investment_analysis(context, [s for s in scenarios if s["parameters"]["room_id"] == room_id], months)
                for room_id, context in contexts.items()]
    maximum = max(Decimal("1"), *(Decimal(s["results"]["series"][months]["total_cost"]) for s in scenarios))
    lines = [{"name": s["parameters"]["name"], "color": ("#0f766e", "#2563eb")[index],
        "points": " ".join(f"{60 + row['month'] / months * 660:.2f},{240 - float(Decimal(row['total_cost']) / maximum) * 210:.2f}"
            for row in s["results"]["series"][:months + 1])} for index, s in enumerate(scenarios)]
    return templates.TemplateResponse(request=request, name="cost_report.html", context={"scenarios": scenarios,
        "contexts": contexts, "analyses": analyses, "comparison": comparison, "months": months,
        "issued": datetime.now(timezone.utc), "lines": lines, "maximum": maximum})


@router.get("/report")
def export_report(
    scenario_id: list[str] = Query(..., min_length=1, max_length=2),
    months: int = Query(12), db: Session = Depends(get_db),
    tariff_mode: Literal["shared", "scenario"] = "shared",
    common_tariff_per_kwh: Decimal | None = Query(None, ge=0, le=1000, max_digits=12, decimal_places=6),
    days: int = Query(7, ge=1, le=366),
):
    if months not in (12, 24, 36) or len(set(scenario_id)) != len(scenario_id):
        raise HTTPException(422, "Selecione um ou dois cenários distintos e 12, 24 ou 36 meses")
    scenarios = [scenario_result(db, get_scenario(db, value)) for value in scenario_id]
    comparison = None
    if tariff_mode == "scenario" and common_tariff_per_kwh is not None:
        raise HTTPException(422, "A tarifa comum só pode ser usada no modo de tarifa compartilhada")
    if len(scenarios) == 2:
        comparison = comparison_result(CostComparisonInput(scenario_ids=scenario_id, months=months,
            tariff_mode=tariff_mode, common_tariff_per_kwh=common_tariff_per_kwh), db)
        scenarios = comparison["scenarios"]
    elif common_tariff_per_kwh is not None:
        raise HTTPException(422, "A tarifa comum é aplicável apenas à comparação de dois cenários")
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    def write(*values):
        # Avoid spreadsheet formulas when names/notes originate from user input.
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values])

    write("Custos e Investimentos — estimativas, não medições de consumo elétrico")
    write("Emitido em UTC", datetime.now(timezone.utc).isoformat())
    write("Horizonte (meses)", months)
    if comparison:
        basis = comparison["comparison_basis"]
        write("Base da comparação", basis["note"])
        write("Tarifa comum (R$/kWh)", basis["common_tariff_per_kwh"] or "Não aplicada")
    labels = {"room_id": "Identificador da sala", "name": "Cenário", "equipment_model": "Modelo",
        "cooling_capacity_btu_h": "Capacidade de refrigeração (BTU/h)", "average_power_kw": "Potência média informada (kW)",
        "equipment_price": "Preço informado (R$)", "installation_cost": "Instalação informada (R$)",
        "maintenance_cost": "Valor por manutenção (R$)", "maintenance_interval_months": "Intervalo entre manutenções (meses)",
        "hours_per_day": "Horas de uso por dia", "days_per_month": "Dias de uso por mês", "tariff_per_kwh": "Tarifa informada (R$/kWh)",
        "method": "Método", "label_energy_kwh": "Consumo da etiqueta (kWh)", "label_reference_hours": "Horas de referência da etiqueta",
        "label_period": "Período de referência da etiqueta", "parameter_source": "Fonte dos parâmetros", "notes": "Observações"}
    for scenario in scenarios:
        write()
        write("Sala", scenario["room_name"])
        write("Identificador do cenário", scenario["id"])
        context = environmental_context(db, get_room(db, scenario["parameters"]["room_id"]), days)
        write("Período ambiental (UTC)", context["start"].isoformat(), context["end"].isoformat())
        for key in ("temperature_avg", "humidity_avg", "alerts", "critical", "outside_seconds", "coverage_percent"):
            write("Indicador ambiental: " + key, context[key] if context[key] is not None else "Não calculável")
        write("Metodologia ambiental", context["methodology"])
        write("Análise do investimento", investment_analysis(context, [scenario], months))
        if "original_parameters" in scenario:
            write("Tarifa original salva (R$/kWh)", scenario["original_parameters"]["tariff_per_kwh"])
        for key, value in scenario["parameters"].items():
            write(labels.get(key, key), value if value is not None else "Não informado")
        result = scenario["results"]
        for label, key in [("Consumo mensal estimado (kWh)", "monthly_energy_kwh"), ("Custo mensal estimado (R$)", "monthly_cost"),
                           ("Custo anual de energia (R$)", "annual_cost"), ("Investimento inicial (R$)", "initial_investment")]:
            write(label, result[key])
        write("Manutenção anual prevista (R$)", result["annual_maintenance_cost"] if result["maintenance_informed"] else "Não informado; não incluído no total")
        write("Custo operacional anual previsto (R$)", result["annual_operating_cost"])
        for projection in result["projections"]:
            write(f"Total projetado em {projection['months']} meses (R$)", projection["total_cost"])
        write("Versão da metodologia", result["methodology_version"])
        for formula in result["formulas"]:
            write("Fórmula", formula)
        for limitation in result["limitations"]:
            write("Limitação", limitation)
        write("Referência metodológica", result["reference_url"])
        write("Mês", "Energia no mês (R$)", "Energia acumulada (R$)", "Manutenção no mês (R$)", "Manutenção acumulada (R$)", "Total com investimento (R$)")
        for row in result["series"][:months + 1]:
            write(row["month"], row["energy_cost"], row["cumulative_energy_cost"],
                  row["maintenance_cost"] if result["maintenance_informed"] else "Não informado",
                  row["cumulative_maintenance_cost"] if result["maintenance_informed"] else "Não informado", row["total_cost"])
    if len(scenarios) == 2:
        a, b = [item["results"] for item in scenarios]
        write()
        write("Comparação B menos A", "A: " + scenarios[0]["parameters"]["name"], "B: " + scenarios[1]["parameters"]["name"])
        write("Diferença mensal de energia (R$)", Decimal(b["monthly_cost"]) - Decimal(a["monthly_cost"]))
        write("Diferença de investimento (R$)", Decimal(b["initial_investment"]) - Decimal(a["initial_investment"]))
        write(f"Diferença de custo total em {months} meses (R$)", Decimal(b["series"][months]["total_cost"]) - Decimal(a["series"][months]["total_cost"]))
        write("Interpretação", "Diferença positiva: B tem maior custo; negativa: B tem menor custo. Não é garantia de economia.")
        write("Menor custo projetado", comparison["lowest_total_cost_scenario_id"] or "Empate")
        write("Limite da comparação", comparison["interpretation"])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="custos_investimentos.csv"'})
