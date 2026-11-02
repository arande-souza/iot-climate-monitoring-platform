"""Move existing example references from 24 months to 17 consecutive months."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from add_planning_scenarios import planning_payloads
from app.database import engine
from app.models.cost_scenario import CostScenario
from app.models.room import Room
from app.schemas.cost_schema import CostScenarioInput


def main():
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    changes, backup, report = [], [], []
    with Session(engine) as db, db.begin():
        rooms = db.scalars(select(Room).where(Room.is_deleted.is_(False), Room.name.in_(["Sala 1", "Sala 2"])).order_by(Room.name)).all()
        if [r.name for r in rooms] != ["Sala 1", "Sala 2"]:
            raise RuntimeError("As duas salas devem ser identificadas sem ambiguidade")
        for room_index, room in enumerate(rooms):
            old = list(planning_payloads(room, room_index, "spread24", today))
            new = list(planning_payloads(room, room_index, "monthly17", today))
            for (scenario_id, expected), (_, target) in zip(old, new):
                scenario = db.get(CostScenario, scenario_id)
                if scenario is None:
                    raise RuntimeError("Cenário de exemplo original não encontrado")
                current = CostScenarioInput.model_validate(scenario)
                # Also permit a repeated run after this exact correction.
                if current.model_dump() == target.model_dump():
                    continue
                if current.model_dump() != expected.model_dump():
                    raise RuntimeError("Um cenário foi editado; interrompido para preservar os dados")
                backup.append({"id": scenario.id, "parameters": current.model_dump(mode="json"),
                    "created_at": scenario.created_at.isoformat(), "updated_at": scenario.updated_at.isoformat()})
                changes.append((scenario, target))
            report.append({"room": room.name, "count": 17, "first": new[0][1].name, "last": new[-1][1].name})
        if backup:
            Path("backups/planning_before_monthly17.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
        for scenario, target in changes:
            # Keep UUID, financial inputs and creation date intact.
            scenario.name, scenario.notes = target.name, target.notes
    result = {"updated": len(changes), "distribution": "monthly17", "rooms": report}
    Path("docs/evidence/costs-monthly17.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
