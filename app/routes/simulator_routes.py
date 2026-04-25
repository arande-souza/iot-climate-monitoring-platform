from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.simulator_schema import (
    SimulatorGenerateRequest,
    SimulatorGenerateResponse,
)
from app.services.simulator_service import (
    MAX_SIMULATED_RECORDS,
    calculate_total_records,
    generate_simulated_readings,
)

router = APIRouter(prefix="/simulator", tags=["simulator"])


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
    if total_records > MAX_SIMULATED_RECORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite de {MAX_SIMULATED_RECORDS} registros por chamada excedido",
        )

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
