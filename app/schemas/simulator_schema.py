from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SimulatorProfile = Literal["normal", "alert", "critical", "mixed"]


class SimulatorGenerateRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=80)
    location: str = Field(..., min_length=1, max_length=120)
    start_datetime: datetime
    end_datetime: datetime
    frequency_seconds: int = Field(..., gt=0)
    profile: SimulatorProfile = "mixed"

    @field_validator("frequency_seconds", mode="before")
    @classmethod
    def reject_invalid_frequency_type(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("frequency_seconds deve ser um inteiro maior que zero")
        return value


class SimulatorGenerateResponse(BaseModel):
    total_generated: int
    start_datetime: datetime
    end_datetime: datetime
    frequency_seconds: int
    device_id: str
    location: str
    profile: SimulatorProfile
