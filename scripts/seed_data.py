from datetime import datetime, timedelta, timezone
from random import choice, uniform

from app.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReading
from app.schemas.sensor_reading_schema import SensorReadingCreate
from app.services.classification_service import classify_environment

DEVICES = [
    ("esp32-sala-01", "Sala de TI"),
    ("esp32-lab-02", "Laboratório de Redes"),
    ("esp32-datacenter-03", "Sala de Servidores"),
]


def make_payload(index: int) -> SensorReadingCreate:
    device_id, location = choice(DEVICES)
    return SensorReadingCreate(
        device_id=device_id,
        location=location,
        temperature=round(uniform(20.5, 27.8), 1),
        humidity=round(uniform(34.0, 68.0), 1),
        pressure=round(uniform(1008.0, 1018.0), 1),
        co2=round(uniform(620, 1320), 0),
        pm25=round(uniform(4.0, 31.0), 1),
        pm10=round(uniform(8.0, 58.0), 1),
    )


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        base_time = datetime.now(timezone.utc) - timedelta(hours=6)
        for index in range(72):
            payload = make_payload(index)
            reading = SensorReading(
                **payload.model_dump(),
                air_quality_status=classify_environment(payload),
                created_at=base_time + timedelta(minutes=index * 5),
            )
            db.add(reading)
        db.commit()
        print("72 leituras fictícias inseridas com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
