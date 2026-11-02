from decimal import Decimal, ROUND_HALF_UP

from app.schemas.cost_schema import CostScenarioInput

METHODOLOGY_VERSION = "1.1"
REFERENCE_URL = "https://www.gov.br/inmetro/pt-br/assuntos/regulamentacao/avaliacao-da-conformidade/programa-brasileiro-de-etiquetagem/tabelas-de-eficiencia-energetica/condicionadores-de-ar/nova-etiqueta"
LIMITATIONS = [
    "Resultados estimados, não medições de consumo elétrico nem garantia de economia.",
    "BTU/h expressa capacidade de refrigeração e não é convertido em potência elétrica em kW.",
    "Temperatura, umidade e alertas ambientais não são utilizados para deduzir consumo elétrico.",
    "Tarifa, dias e horas de uso permanecem constantes em todos os meses; não há sazonalidade, reajustes ou inflação.",
    "Manutenção só é incluída quando informada; ausência de valor não significa custo real zero. Não inclui financiamento, depreciação, custos fixos da conta ou encargos não incorporados à tarifa informada.",
    "Manutenção prevista ao fim de cada intervalo informado, sem ocorrência no mês zero e sem reajustes; não é rateada entre meses.",
    "Consumo varia com carga térmica, isolamento, ocupação, ajuste de temperatura, manutenção e funcionamento do compressor.",
    "No método por etiqueta, o rateio por horas é uma aproximação linear de condições padronizadas; não reproduz o desempenho sazonal real.",
    "Preços, potência, tarifa e referências são fornecidos pelo usuário; não são cotações verificadas pelo sistema.",
    "Valores são arredondados somente para apresentação; totais usam os valores não arredondados.",
]


def rounded(value, places="0.01"):
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def calculate_costs(payload: CostScenarioInput):
    hours = payload.hours_per_day * payload.days_per_month
    if payload.method == "power":
        rate = payload.average_power_kw
        formula = "Consumo mensal (kWh) = potência média estimada (kW) × horas/dia × dias/mês"
    else:
        rate = payload.label_energy_kwh / payload.label_reference_hours
        formula = "Consumo mensal (kWh) = (consumo da etiqueta em kWh ÷ horas de referência do mesmo período) × horas/dia × dias/mês"
    monthly_energy = rate * hours
    monthly_cost = monthly_energy * payload.tariff_per_kwh
    initial = payload.equipment_price + payload.installation_cost
    maintenance_informed = payload.maintenance_cost is not None

    def maintenance(month):
        if not maintenance_informed:
            return Decimal("0")
        return payload.maintenance_cost * (month // payload.maintenance_interval_months)

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "monthly_hours": hours,
        "monthly_energy_kwh": rounded(monthly_energy, "0.0001"),
        "monthly_cost": rounded(monthly_cost),
        "annual_cost": rounded(monthly_cost * 12),
        "initial_investment": rounded(initial),
        "equipment_cost": rounded(payload.equipment_price),
        "installation_cost": rounded(payload.installation_cost),
        "maintenance_informed": maintenance_informed,
        "annual_maintenance_cost": rounded(maintenance(12)) if maintenance_informed else None,
        "annual_operating_cost": rounded(monthly_cost * 12 + maintenance(12)),
        "projections": [{"months": month, "energy_cost": rounded(monthly_cost * month),
                         "maintenance_cost": rounded(maintenance(month)) if maintenance_informed else None,
                         "operating_cost": rounded(monthly_cost * month + maintenance(month)),
                         "total_cost": rounded(initial + monthly_cost * month + maintenance(month))} for month in (12, 24, 36)],
        "series": [{"month": month, "energy_cost": rounded(monthly_cost) if month else Decimal("0.00"),
                    "cumulative_energy_cost": rounded(monthly_cost * month),
                    "maintenance_cost": rounded(maintenance(month) - maintenance(max(0, month - 1))) if maintenance_informed else None,
                    "cumulative_maintenance_cost": rounded(maintenance(month)) if maintenance_informed else None,
                    "operating_cost": rounded((monthly_cost if month else Decimal("0")) + maintenance(month) - maintenance(max(0, month - 1))),
                    "cumulative_operating_cost": rounded(monthly_cost * month + maintenance(month)),
                    "total_cost": rounded(initial + monthly_cost * month + maintenance(month))} for month in range(37)],
        "formulas": [formula,
            "Custo mensal (R$) = consumo mensal estimado (kWh) × tarifa (R$/kWh)",
            "Custo anual de energia (R$) = custo mensal não arredondado × 12",
            "Investimento inicial (R$) = preço do equipamento + instalação",
            "Manutenção acumulada em N meses (R$) = valor por manutenção × parte inteira de (N ÷ intervalo em meses), quando informada",
            "Custo acumulado em N meses (R$) = investimento inicial + custo mensal de energia não arredondado × N + manutenção prevista informada"],
        "limitations": LIMITATIONS,
        "reference_url": REFERENCE_URL,
    }
