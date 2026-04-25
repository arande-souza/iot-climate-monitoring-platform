from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.sensor_reading import SensorReading
from app.schemas.simulator_schema import (
    SimulatorGenerateRequest,
    SimulatorGenerateResponse,
    SimulatorUpdateUntilNowRequest,
    SimulatorUpdateUntilNowResponse,
)
from app.services.simulator_service import (
    MAX_SIMULATED_RECORDS,
    calculate_total_records,
    generate_simulated_readings,
)

router = APIRouter(prefix="/simulator", tags=["simulator"])
DEFAULT_EMPTY_DATABASE_LOOKBACK_HOURS = 24
UPDATE_COOLDOWN_SECONDS = 60


def ensure_generation_limit(total_records: int) -> None:
    if total_records > MAX_SIMULATED_RECORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite de {MAX_SIMULATED_RECORDS} registros por chamada excedido",
        )


@router.post("/generate", response_model=SimulatorGenerateResponse)
def generate_history(payload: SimulatorGenerateRequest, db: Session = Depends(get_db)):
    if payload.end_datetime <= payload.start_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_datetime deve ser maior que start_datetime",
        )

    total_records = calculate_total_records(
        payload.start_datetime,
        payload.end_datetime,
        payload.frequency_seconds,
    )
    ensure_generation_limit(total_records)

    total_generated = generate_simulated_readings(db, payload)
    return SimulatorGenerateResponse(
        total_generated=total_generated,
        start_datetime=payload.start_datetime,
        end_datetime=payload.end_datetime,
        frequency_seconds=payload.frequency_seconds,
        device_id=payload.device_id,
        location=payload.location,
        profile=payload.profile,
    )


@router.post("/update-until-now", response_model=SimulatorUpdateUntilNowResponse)
def update_until_now(
    payload: SimulatorUpdateUntilNowRequest,
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    last_created_at = db.scalar(select(func.max(SensorReading.created_at)))

    if last_created_at is None:
        start_datetime = now - timedelta(hours=DEFAULT_EMPTY_DATABASE_LOOKBACK_HOURS)
    else:
        if last_created_at.tzinfo is None:
            last_created_at = last_created_at.replace(tzinfo=timezone.utc)
        if now - last_created_at < timedelta(seconds=UPDATE_COOLDOWN_SECONDS):
            return SimulatorUpdateUntilNowResponse(
                message="Coleta atualizada, aguarde pelo menos 60s",
                start_datetime=last_created_at,
                end_datetime=now,
                total_generated=0,
            )
        start_datetime = last_created_at + timedelta(seconds=payload.frequency_seconds)

    if start_datetime >= now:
        return SimulatorUpdateUntilNowResponse(
            message="Nenhum dado novo para gerar",
            start_datetime=start_datetime,
            end_datetime=now,
            total_generated=0,
        )

    total_records = calculate_total_records(
        start_datetime,
        now,
        payload.frequency_seconds,
    )
    ensure_generation_limit(total_records)

    generate_payload = SimulatorGenerateRequest(
        device_id=payload.device_id,
        location=payload.location,
        start_datetime=start_datetime,
        end_datetime=now,
        frequency_seconds=payload.frequency_seconds,
        profile=payload.profile,
    )
    total_generated = generate_simulated_readings(db, generate_payload)
    return SimulatorUpdateUntilNowResponse(
        message="Base simulada atualizada com sucesso",
        start_datetime=start_datetime,
        end_datetime=now,
        total_generated=total_generated,
    )
