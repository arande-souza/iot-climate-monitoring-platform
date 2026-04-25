from app.schemas.sensor_reading_schema import SensorReadingCreate

STATUS_RANK = {
    "ideal": 0,
    "aceitavel": 1,
    "alerta": 2,
    "critico": 3,
}


def classify_temperature(value: float) -> str:
    if 22 <= value <= 24:
        return "ideal"
    if 20 <= value <= 26:
        return "aceitavel"
    return "alerta"


def classify_humidity(value: float) -> str:
    if 40 <= value <= 60:
        return "ideal"
    if 30 <= value <= 65:
        return "aceitavel"
    return "alerta"


def classify_co2(value: float) -> str:
    if value > 1500:
        return "critico"
    if value > 1000:
        return "alerta"
    if value <= 800:
        return "ideal"
    return "aceitavel"


def classify_pm25(value: float) -> str:
    if value > 35:
        return "critico"
    if value >= 12:
        return "alerta"
    return "ideal"


def classify_environment(reading: SensorReadingCreate) -> str:
    statuses = [
        classify_temperature(reading.temperature),
        classify_humidity(reading.humidity),
        classify_co2(reading.co2),
        classify_pm25(reading.pm25),
    ]
    return max(statuses, key=lambda status: STATUS_RANK[status])


def build_recommendations(status: str) -> list[str]:
    if status == "ideal":
        return ["Ambiente dentro das faixas ideais."]
    if status == "aceitavel":
        return ["Ambiente operacional, mas recomenda-se acompanhar tendências."]
    if status == "alerta":
        return [
            "Verificar climatização, ventilação e possíveis fontes de particulados.",
            "Acompanhar sensores para evitar impacto em conforto e equipamentos.",
        ]
    return [
        "Ação imediata recomendada: revisar ventilação e climatização.",
        "Avaliar permanência de pessoas e risco para equipamentos sensíveis.",
    ]
