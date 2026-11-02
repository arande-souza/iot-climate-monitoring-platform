"""Replace all sensor readings with two simulated rooms, saving a CSV backup first."""

import argparse
import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import delete, func, insert, select, text

from app.database import engine
from app.models.sensor_reading import SensorReading
from app.models.room import Room
from app.schemas.sensor_reading_schema import SensorReadingCreate
from app.services.classification_service import classify_environment
from app.services.simulator_service import calculate_total_records, generate_values

BRASILIA = timezone(timedelta(hours=-3))
ROOMS = [("esp32-sala-01", "Santo André - SP"), ("esp32-sala-02", "Sala 2")]


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Informe o fuso horario, por exemplo: 2026-08-10T00:00:00-03:00")
    return parsed.astimezone(BRASILIA)


def rebuild_readings(start, end, frequency_seconds=60, backup_dir=Path("backups"), apply=False):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("As datas precisam incluir fuso horario")
    if start >= end or frequency_seconds <= 0:
        raise ValueError("Periodo ou frequencia invalida")
    start, end = start.astimezone(BRASILIA), end.astimezone(BRASILIA)
    per_room = calculate_total_records(start, end, frequency_seconds)
    print(f"Periodo: {start.isoformat()} ate {end.isoformat()}", flush=True)
    print(f"Plano: {per_room} leituras por sala; {per_room * len(ROOMS)} no total", flush=True)
    table = SensorReading.__table__
    with engine.begin() as connection:
        if apply and connection.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            connection.execute(text("LOCK TABLE sensor_readings IN EXCLUSIVE MODE"))
        previous = connection.scalar(select(func.count()).select_from(table))
        print(f"Leituras existentes a substituir: {previous}", flush=True)
        if not apply:
            print("Somente consulta. Use --apply para salvar backup e substituir as leituras.")
            return {"previous": previous, "per_room": per_room}

        locations = {}
        registered = {}
        for device_id, default_location in ROOMS:
            row = connection.execute(select(Room.__table__).where(
                Room.device_id == device_id, Room.is_deleted.is_(False),
            )).mappings().first()
            if row is None:
                raise ValueError(f"Sala nao cadastrada ou excluida: {device_id}")
            registered[device_id] = SimpleNamespace(**row)
            locations[device_id] = connection.scalar(
                select(table.c.location).where(table.c.device_id == device_id)
                .order_by(table.c.created_at.desc(), table.c.id.desc()).limit(1)
            ) or default_location

        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = backup_dir / f"sensor_readings_before_reset_{stamp}.csv"
        with backup_path.open("x", encoding="utf-8-sig", newline="") as backup:
            writer = csv.writer(backup)
            writer.writerow(table.columns.keys())
            rows = connection.execute(select(table).execution_options(yield_per=2000))
            for row in rows:
                writer.writerow([
                    value.isoformat() if isinstance(value, datetime) else value
                    for value in row
                ])
            rows.close()
            backup.flush()
            os.fsync(backup.fileno())
        print(f"Backup salvo: {backup_path.resolve()}", flush=True)

        connection.execute(delete(table))
        for device_id, _ in ROOMS:
            current = start
            batch = []
            for index in range(per_room):
                payload = SensorReadingCreate(
                    device_id=device_id, location=locations[device_id],
                    data_source="simulation",
                    **generate_values(current, "mixed"),
                )
                batch.append({
                    **payload.model_dump(), "created_at": current.astimezone(timezone.utc),
                    "room_id": registered[device_id].id,
                    "air_quality_status": classify_environment(payload, registered[device_id]),
                })
                current += timedelta(seconds=frequency_seconds)
                if len(batch) == 2000 or index == per_room - 1:
                    connection.execute(insert(table), batch)
                    batch.clear()
            print(f"{device_id}: {per_room} leituras geradas", flush=True)
    print("Substituicao concluida e confirmada no banco.", flush=True)
    return {"previous": previous, "per_room": per_room, "backup": backup_path}


def main():
    from app.services.storage_service import initialize_storage

    initialize_storage()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=parse_datetime)
    parser.add_argument("--end", type=parse_datetime)
    parser.add_argument("--frequency-seconds", type=int, default=60)
    parser.add_argument("--backup-dir", type=Path, default=Path("backups"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rebuild_readings(
        args.start, args.end or datetime.now(BRASILIA).replace(microsecond=0),
        args.frequency_seconds, args.backup_dir, args.apply,
    )


if __name__ == "__main__":
    main()
