import argparse
import csv
from datetime import datetime
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReading
from app.services.room_service import ensure_device_room
from app.services.storage_service import initialize_storage

STATUS_MAP = {
    "normal": "ideal",
    "ideal": "ideal",
    "acceptable": "aceitavel",
    "aceitavel": "aceitavel",
    "alert": "alerta",
    "alerta": "alerta",
    "critical": "critico",
    "critico": "critico",
}


def parse_float(value: str) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_datetime(value: str) -> datetime:
    value = value.strip()
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def normalize_status(value: str) -> str:
    normalized = (value or "").strip().lower()
    return STATUS_MAP.get(normalized, normalized or "ideal")


def iter_csv_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield {
                "device_id": row["device_id"].strip(),
                "location": row["location"].strip(),
                "data_source": row.get("data_source") or "unknown",
                "temperature": parse_float(row["temperature"]),
                "humidity": parse_float(row["humidity"]),
                "pressure": parse_float(row.get("pressure")),
                "co2": parse_float(row["co2"]),
                "pm25": parse_float(row["pm25"]),
                "pm10": parse_float(row.get("pm10")),
                "air_quality_status": normalize_status(row.get("air_quality_status", "")),
                "created_at": parse_datetime(row["created_at"]),
            }


def import_csv(csv_path: Path, batch_size: int) -> int:
    initialize_storage()
    db = SessionLocal()
    total = 0
    batch = []
    device_rooms = {}

    try:
        for row in iter_csv_rows(csv_path):
            if row["data_source"] not in {"simulation", "sensor", "external_api", "unknown"}:
                raise ValueError("Origem de dados invalida no CSV")
            if row["device_id"] not in device_rooms:
                device_rooms[row["device_id"]] = ensure_device_room(
                    db, row["device_id"], row["location"], row["data_source"],
                ).id
            row["room_id"] = device_rooms[row["device_id"]]
            batch.append(row)
            if len(batch) >= batch_size:
                db.bulk_insert_mappings(SensorReading, batch)
                db.commit()
                total += len(batch)
                print(f"{total} registros importados...")
                batch.clear()

        if batch:
            db.bulk_insert_mappings(SensorReading, batch)
            db.commit()
            total += len(batch)

        return total
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa leituras ambientais de um CSV.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="sensor_readings_seed.csv",
        help="Caminho do arquivo CSV. Padrao: sensor_readings_seed.csv",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    csv_path = Path(args.csv_path).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV nao encontrado: {csv_path}")

    total = import_csv(csv_path, args.batch_size)
    print(f"Importacao concluida: {total} registros inseridos.")


if __name__ == "__main__":
    main()
