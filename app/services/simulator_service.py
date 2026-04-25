from datetime import datetime, timedelta
from random import gauss, random, uniform

from sqlalchemy.orm import Session

from app.models.sensor_reading import SensorReading
from app.schemas.sensor_reading_schema import SensorReadingCreate
from app.schemas.simulator_schema import SimulatorGenerateRequest
from app.services.classification_service import classify_environment

MAX_SIMULATED_RECORDS = 100_000


def calculate_total_records(start: datetime, end: datetime, frequency_seconds: int) -> int:
    return int((end - start).total_seconds() // frequency_seconds) + 1


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def choose_effective_profile(profile: str) -> str:
    if profile != "mixed":
        return profile

    roll = random()
    if roll < 0.65:
        return "normal"
    if roll < 0.9:
        return "alert"
    return "critical"


def business_hours_factor(moment: datetime) -> float:
    hour = moment.hour + moment.minute / 60
    if hour < 8 or hour > 18:
        return 0.15
    if hour <= 12:
        return (hour - 8) / 4
    return max(0.45, 1 - (hour - 12) / 10)


def afternoon_temperature_boost(moment: datetime) -> float:
    hour = moment.hour + moment.minute / 60
    if hour < 8:
        return -0.8
    if hour <= 15:
        return (hour - 8) * 0.22
    return max(0, 1.54 - (hour - 15) * 0.18)


def generate_values(moment: datetime, profile: str) -> dict[str, float]:
    effective_profile = choose_effective_profile(profile)
    occupancy = business_hours_factor(moment)
    temp_boost = afternoon_temperature_boost(moment)

    temperature = gauss(24, 2) + temp_boost
    humidity = gauss(65, 10) - (temperature - 24) * 2.2
    co2 = gauss(600, 200) + occupancy * 280
    pm25 = gauss(12, 8)
    pm10 = gauss(25, 12)
    pressure = gauss(1013, 5)

    if random() < 0.04:
        pm25 += uniform(10, 28)
        pm10 += uniform(18, 45)

    if effective_profile == "normal":
        temperature = clamp(gauss(23.1, 0.65) + temp_boost * 0.2, 22, 24)
        humidity = clamp(gauss(52, 5) - (temperature - 23) * 1.4, 40, 60)
        co2 = clamp(gauss(620, 80) + occupancy * 90, 420, 800)
        pm25 = clamp(gauss(7, 2.5), 1, 11.8)
        pm10 = clamp(gauss(18, 5), 3, 35)
    elif effective_profile == "alert":
        if random() < 0.45:
            temperature = uniform(26.2, 30.5)
            humidity = uniform(22, 34)
        if random() < 0.45:
            co2 = uniform(1005, 1480)
        if random() < 0.4:
            pm25 = uniform(12, 35)
            pm10 = uniform(36, 85)
    elif effective_profile == "critical":
        temperature = temperature + uniform(0.5, 3.0)
        humidity = humidity - uniform(5, 18)
        if random() < 0.72:
            co2 = uniform(1501, 2600)
        else:
            co2 = uniform(1005, 1500)
        if random() < 0.68:
            pm25 = uniform(35.1, 95)
            pm10 = uniform(80, 180)
        else:
            pm25 = uniform(18, 35)
            pm10 = uniform(40, 90)

    return {
        "temperature": round(clamp(temperature, -10, 45), 1),
        "humidity": round(clamp(humidity, 5, 100), 1),
        "pressure": round(clamp(pressure, 980, 1035), 1),
        "co2": round(clamp(co2, 350, 5000), 0),
        "pm25": round(clamp(pm25, 0, 250), 1),
        "pm10": round(clamp(pm10, 0, 400), 1),
    }


def generate_simulated_readings(db: Session, payload: SimulatorGenerateRequest) -> int:
    total = calculate_total_records(
        payload.start_datetime,
        payload.end_datetime,
        payload.frequency_seconds,
    )

    readings = []
    current = payload.start_datetime
    for _ in range(total):
        values = generate_values(current, payload.profile)
        sensor_payload = SensorReadingCreate(
            device_id=payload.device_id,
            location=payload.location,
            **values,
        )
        readings.append(
            SensorReading(
                **sensor_payload.model_dump(),
                air_quality_status=classify_environment(sensor_payload),
                created_at=current,
            )
        )
        current += timedelta(seconds=payload.frequency_seconds)

    db.add_all(readings)
    db.commit()
    return total
