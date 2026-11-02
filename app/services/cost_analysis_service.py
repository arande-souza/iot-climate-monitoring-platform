"""Environmental context and deterministic narrative; never infer electrical use."""
from decimal import Decimal

from sqlalchemy import select

from app.models.sensor_reading import SensorReading as Reading
from app.services.room_analytics_service import aware, period, room_snapshot

MAX_GAP_SECONDS = 30 * 60


def environmental_context(db, room, days=7):
    start, end = period(days=days)
    rows = db.execute(select(Reading.created_at, Reading.temperature, Reading.humidity,
        Reading.air_quality_status, Reading.data_source).where(
            Reading.room_id == room.id, Reading.created_at >= start, Reading.created_at <= end,
        ).order_by(Reading.created_at, Reading.id)).yield_per(2000)
    count = alerts = critical = excluded = 0
    temperature = humidity = covered = outside = 0.0
    previous = None
    for row in rows:
        valid = (row.temperature is not None and row.humidity is not None
                 and -40 <= row.temperature <= 85 and 0 <= row.humidity <= 100
                 and row.data_source != "external_api")
        if not valid:
            excluded += 1
            previous = None
            continue
        at = aware(row.created_at)
        is_outside = not (room.temperature_min <= row.temperature <= room.temperature_max
                          and room.humidity_min <= row.humidity <= room.humidity_max)
        count += 1
        temperature += row.temperature
        humidity += row.humidity
        alerts += row.air_quality_status in ("alerta", "alert")
        critical += row.air_quality_status in ("critico", "critical")
        if previous:
            seconds = (at - previous[0]).total_seconds()
            if 0 < seconds <= MAX_GAP_SECONDS:
                covered += seconds
                if previous[1]:
                    outside += seconds
        previous = (at, is_outside)
    snapshot = room_snapshot(db, room)
    return {"room": snapshot["room"], "start": start, "end": end,
        "latest_reading": snapshot["latest_reading"], "stale": snapshot["stale"],
        "count": count, "excluded_count": excluded,
        "temperature_avg": temperature / count if count else None,
        "humidity_avg": humidity / count if count else None,
        "alerts": alerts, "critical": critical,
        "outside_seconds": outside if covered else None,
        "covered_seconds": covered, "unknown_seconds": max(0, (end - start).total_seconds() - covered),
        "coverage_percent": covered / (end - start).total_seconds() * 100,
        "methodology": "Alertas e críticos contam leituras com a classificação histórica registrada, não episódios. "
            "Tempo fora dos limites usa os limites atuais de temperatura e umidade e mantém o estado da leitura anterior "
            "somente até a próxima leitura válida, com intervalo máximo de 30 minutos. Leituras inválidas ou referências "
            "externas interrompem a continuidade. Lacunas e bordas do período ficam sem cobertura; não são tempo normal. "
            "Médias aritméticas das leituras válidas; referências externas excluídas. "
            "Esse contexto não determina consumo elétrico nem comprova adequação do equipamento."}


def brl(value):
    return "R$ " + f"{Decimal(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def investment_analysis(context, scenarios, months):
    room = context["room"]
    parts = [f"A sala {room.name} apresentou {context['alerts']} leituras em alerta e "
             f"{context['critical']} críticas no período analisado, entre {context['count']} leituras válidas."]
    if not context["count"]:
        parts = [f"A sala {room.name} não possui leituras ambientais válidas no período analisado."]
    for scenario in scenarios:
        r, p = scenario["results"], scenario["parameters"]
        total = r["series"][months]["total_cost"]
        parts.append(f"O cenário {p['name']} tem investimento inicial estimado de {brl(r['initial_investment'])}, "
            f"energia mensal de {brl(r['monthly_cost'])} e total projetado de {brl(total)} em {months} meses.")
        if not r["maintenance_informed"]:
            parts.append("Manutenção não informada: seu custo não está incluído no total deste cenário.")
    if len(scenarios) == 2:
        totals = [Decimal(s["results"]["series"][months]["total_cost"]) for s in scenarios]
        if totals[0] == totals[1]:
            parts.append("Os cenários têm o mesmo custo total projetado.")
        else:
            index = 0 if totals[0] < totals[1] else 1
            parts.append(f"{scenarios[index]['parameters']['name']} apresenta menor custo projetado, "
                         f"com diferença de {brl(abs(totals[1] - totals[0]))} no período.")
    parts.append("Os valores são estimativas com parâmetros informados, não medições elétricas. Menor custo não "
        "comprova melhor climatização, economia real ou retorno do investimento; o dimensionamento requer dados técnicos.")
    return " ".join(parts)
