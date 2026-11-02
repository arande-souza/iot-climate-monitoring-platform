from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


DataSource = Literal["sensor", "simulation", "external_api", "unknown"]


class SourceConfig(BaseModel):
    external_api_url: HttpUrl | None = None
    notes: str = Field(default="", max_length=500)


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[\w.:-]+$")
    location: str = Field(min_length=1, max_length=120)
    identifier: str = Field(default="", max_length=80)
    city: str = Field(default="", max_length=120)
    state: str = Field(default="", max_length=2, pattern=r"^([A-Z]{2})?$")
    internal_location: str = Field(default="", max_length=120)
    temperature_min: float = Field(default=20, ge=-40, le=85, allow_inf_nan=False)
    temperature_max: float = Field(default=26, ge=-40, le=85, allow_inf_nan=False)
    humidity_min: float = Field(default=30, ge=0, le=100, allow_inf_nan=False)
    humidity_max: float = Field(default=65, ge=0, le=100, allow_inf_nan=False)
    data_source: DataSource = "simulation"
    source_config: SourceConfig = Field(default_factory=SourceConfig)

    @field_validator("identifier", "city", "state", "internal_location", mode="before")
    @classmethod
    def normalize_location(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            if info.field_name == "state":
                value = value.upper()
        return value

    @model_validator(mode="after")
    def validate_limits(self):
        self.name, self.location = self.name.strip(), self.location.strip()
        if not self.name or not self.location:
            raise ValueError("Nome e local nao podem ficar vazios")
        if self.temperature_min >= self.temperature_max or self.humidity_min >= self.humidity_max:
            raise ValueError("Cada limite minimo deve ser menor que o maximo")
        return self


class RoomResponse(RoomCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)
