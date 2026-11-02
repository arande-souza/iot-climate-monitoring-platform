from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CostScenarioInput(BaseModel):
    room_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=120)
    equipment_model: str = Field(min_length=1, max_length=160)
    cooling_capacity_btu_h: int = Field(gt=0, le=1_000_000, strict=True)
    method: Literal["power", "label"] = "power"
    average_power_kw: Decimal | None = Field(default=None, gt=0, le=1000, max_digits=14, decimal_places=4)
    equipment_price: Decimal = Field(ge=0, le=1_000_000_000, max_digits=16, decimal_places=2)
    installation_cost: Decimal = Field(ge=0, le=1_000_000_000, max_digits=16, decimal_places=2)
    maintenance_cost: Decimal | None = Field(default=None, ge=0, le=1_000_000_000, max_digits=16, decimal_places=2)
    maintenance_interval_months: int | None = Field(default=None, ge=1, le=120, strict=True)
    hours_per_day: Decimal = Field(ge=0, le=24, max_digits=6, decimal_places=2)
    days_per_month: int = Field(ge=0, le=31, strict=True)
    tariff_per_kwh: Decimal = Field(ge=0, le=1000, max_digits=12, decimal_places=6)
    label_energy_kwh: Decimal | None = Field(default=None, gt=0, le=10_000_000, max_digits=16, decimal_places=4)
    label_reference_hours: Decimal | None = Field(default=None, gt=0, le=8784, max_digits=12, decimal_places=2)
    label_period: Literal["month", "year"] | None = None
    parameter_source: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=2000)

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_method(self):
        if (self.maintenance_cost is None) != (self.maintenance_interval_months is None):
            raise ValueError("Informe o valor e o intervalo em meses da manutenção, ou deixe ambos ausentes")
        self.name, self.equipment_model = self.name.strip(), self.equipment_model.strip()
        self.parameter_source = self.parameter_source.strip()
        if not self.name or not self.equipment_model:
            raise ValueError("Informe o nome do cenário e o modelo do equipamento")
        if self.method == "power" and self.average_power_kw is None:
            raise ValueError("Informe a potência elétrica média estimada em kW")
        if self.method == "label":
            if self.label_energy_kwh is None or self.label_reference_hours is None or not self.label_period:
                raise ValueError("Informe o consumo da etiqueta, o período e as horas de referência desse mesmo período")
            if not self.parameter_source:
                raise ValueError("Identifique a fonte e as condições de referência da etiqueta")
            if self.label_period == "month" and self.label_reference_hours > 744:
                raise ValueError("As horas de referência mensal não podem exceder 744 horas")
        return self


class CostComparisonInput(BaseModel):
    scenario_ids: list[str] = Field(min_length=2, max_length=2)
    months: Literal[12, 24, 36] = 12
    tariff_mode: Literal["shared", "scenario"] = "shared"
    common_tariff_per_kwh: Decimal | None = Field(default=None, ge=0, le=1000, max_digits=12, decimal_places=6)

    @model_validator(mode="after")
    def distinct_scenarios(self):
        if self.tariff_mode == "scenario" and self.common_tariff_per_kwh is not None:
            raise ValueError("A tarifa comum só pode ser usada no modo de tarifa compartilhada")
        if len(set(self.scenario_ids)) != 2:
            raise ValueError("Selecione dois cenários diferentes")
        return self
