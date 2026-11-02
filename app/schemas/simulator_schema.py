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


class SimulatorUpdateOptions(BaseModel):
    frequency_seconds: int = Field(default=60, gt=0)
    profile: SimulatorProfile = "mixed"

    @field_validator("frequency_seconds", mode="before")
    @classmethod
    def reject_invalid_frequency_type(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("frequency_seconds deve ser um inteiro maior que zero")
        return value


class SimulatorUpdateUntilNowRequest(SimulatorUpdateOptions):
    device_id: str = Field(..., min_length=1, max_length=80)
    location: str = Field(..., min_length=1, max_length=120)


class SimulatorUpdateAllRequest(SimulatorUpdateOptions):
    pass


class SimulatorUpdateUntilNowResponse(BaseModel):
    message: str
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    total_generated: int = 0


class SimulatorRoomUpdate(SimulatorUpdateUntilNowResponse):
    room_id: str
    name: str


class SimulatorUpdateAllResponse(BaseModel):
    message: str
    total_rooms: int
    updated_rooms: int
    total_generated: int
    rooms: list[SimulatorRoomUpdate]
