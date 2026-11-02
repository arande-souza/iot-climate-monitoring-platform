from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.room_schema import DataSource


class SensorReadingBase(BaseModel):
    data_source: DataSource = "unknown"
    device_id: str = Field(..., min_length=1, max_length=80, examples=["esp32-sala-01"])
    location: str = Field(..., min_length=1, max_length=120, examples=["Sala de TI"])
    temperature: float = Field(..., ge=-40, le=85)
    humidity: float = Field(..., ge=0, le=100)
    pressure: float | None = Field(default=None, ge=800, le=1200)
    co2: float = Field(..., ge=0, le=10000)
    pm25: float = Field(..., ge=0, le=1000)
    pm10: float | None = Field(default=None, ge=0, le=2000)

    @field_validator(
        "temperature",
        "humidity",
        "pressure",
        "co2",
        "pm25",
        "pm10",
        mode="before",
    )
    @classmethod
    def reject_non_numeric_values(cls, value):
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("valor deve ser numerico")
        return value


class SensorReadingCreate(SensorReadingBase):
    pass


class SensorReadingResponse(SensorReadingBase):
    room_id: str | None = None
    id: int
    air_quality_status: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_timestamp(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    model_config = ConfigDict(from_attributes=True)


class EnvironmentStatus(BaseModel):
    status: str
    latest_reading: SensorReadingResponse | None = None
    recommendations: list[str] = []


class SensorDevice(BaseModel):
    device_id: str
    location: str


class ReadingsDateRange(BaseModel):
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def normalize_timestamp(cls, value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class ReadingsSummary(BaseModel):
    total_readings: int


class PaginatedSensorReadings(BaseModel):
    items: list[SensorReadingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CriticalHourCount(BaseModel):
    hour: int
    alerta: int
    critico: int
    total: int
