"""Add explicitly illustrative planning scenarios, never backdate their creation."""
import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import engine
from app.models.cost_scenario import CostScenario
from app.models.room import Room
from app.schemas.cost_schema import CostScenarioInput
from app.services.cost_service import calculate_costs

# Planning assumptions only; these are not market quotations or manufacturer specifications.
PROFILES = [
    ("Uso reduzido", 9000, "0.65", "2200", "550", "4", 20),
    ("Econômico", 9000, "0.70", "2500", "600", "6", 22),
    ("Escritório", 12000, "0.95", "2900", "650", "8", 22),
    ("Expediente ampliado", 12000, "1.10", "3100", "700", "10", 24),
    ("Uso intensivo", 18000, "1.50", "4200", "850", "12", 26),
    ("Operação contínua", 18000, "1.60", "4500", "900", "24", 30),
]


def planning_payloads(room, room_index, distribution, today):
    current = today.year * 12 + today.month - 1
    for index in range(17):
        # Both options preserve 17 distinct monthly references. No creation date is forged.
        offset = 16 - index if distribution == "monthly17" else 23 - (index * 23 // 16)
        year, month_zero = divmod(current - offset, 12)
        reference = f"{month_zero + 1:02d}/{year}"
        profile, btu, power, price, installation, hours, days = PROFILES[(index + room_index) % len(PROFILES)]
        payload = CostScenarioInput(room_id=room.id,
            name=f"Planejamento {reference} · {profile} (exemplo)",
            equipment_model=f"Referência de planejamento {btu:,} BTU/h".replace(",", "."),
            cooling_capacity_btu_h=btu, method="power", average_power_kw=power,
            equipment_price=price, installation_cost=installation,
            hours_per_day=hours, days_per_month=days, tariff_per_kwh="0.90",
            maintenance_cost=Decimal("120") + Decimal(index % 3) * 30,
            maintenance_interval_months=6 if index % 2 == 0 else 12,
            parameter_source="Exemplo de planejamento cadastrado a pedido do usuário. Valores hipotéticos para explorar o módulo; "
                "não são cotações, tarifas históricas, especificações verificadas nem consumo medido.",
            notes=f"Mês de referência do planejamento: {reference}. Cadastro realizado na data atual. "
                "A referência mensal não representa uma compra ou despesa comprovada nesse mês. "
                "Potência elétrica média informada independentemente da capacidade em BTU/h. "
                "Tarifa constante assumida: R$ 0,90/kWh. Substitua os parâmetros por orçamento, ficha técnica e tarifa aplicáveis. "
                "Cada registro é uma alternativa independente: não some seus investimentos como despesas mensais da sala.")
        scenario_id = str(uuid5(NAMESPACE_URL, f"iot-climate/planning-examples/v1/{room.id}/{year}-{month_zero + 1:02d}"))
        yield scenario_id, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", choices=("monthly17", "spread24"), required=True)
    parser.add_argument("--apply", action="store_true", help="Without this flag, only validate and show the plan")
    args = parser.parse_args()
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    report = {"applied": args.apply, "distribution": args.distribution, "rooms": []}
    with Session(engine) as db, db.begin():
        rooms = db.scalars(select(Room).where(Room.is_deleted.is_(False), Room.name.in_(["Sala 1", "Sala 2"])).order_by(Room.name)).all()
        if [room.name for room in rooms] != ["Sala 1", "Sala 2"]:
            raise RuntimeError("É necessário identificar exatamente uma Sala 1 e uma Sala 2 ativas")
        for room_index, room in enumerate(rooms):
            entries = list(planning_payloads(room, room_index, args.distribution, today))
            added = skipped = 0
            for scenario_id, payload in entries:
                result = calculate_costs(payload)
                assert result["monthly_energy_kwh"] > 0 and result["initial_investment"] > 0
                existing = db.get(CostScenario, scenario_id)
                if existing is not None:
                    if CostScenarioInput.model_validate(existing).model_dump() != payload.model_dump():
                        raise RuntimeError("Um exemplo anterior foi editado; execução interrompida para preservá-lo")
                    skipped += 1
                else:
                    if args.apply:
                        db.add(CostScenario(id=scenario_id, **payload.model_dump()))
                    added += 1
            report["rooms"].append({"name": room.name, "planned": len(entries), "new": added, "already_present": skipped,
                "first": entries[0][1].name, "last": entries[-1][1].name})
    Path("backups").mkdir(exist_ok=True)
    Path("backups/planning_scenarios_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
