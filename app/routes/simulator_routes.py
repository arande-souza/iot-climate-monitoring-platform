from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.sensor_reading import SensorReading
from app.models.room import Room
from app.schemas.simulator_schema import (
    SimulatorGenerateRequest,
    SimulatorGenerateResponse,
    SimulatorUpdateUntilNowRequest,
    SimulatorUpdateUntilNowResponse,
    SimulatorUpdateAllRequest,
    SimulatorUpdateAllResponse,
    SimulatorRoomUpdate,
)
from app.services.simulator_service import (
    MAX_SIMULATED_RECORDS,
    calculate_total_records,
    generate_simulated_readings,
)
from app.services.room_service import ensure_device_room

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
    room = ensure_device_room(db, payload.device_id, payload.location, "simulation")
    last_created_at = db.scalar(
        select(func.max(SensorReading.created_at)).where(
            SensorReading.room_id == room.id,
        )
    )

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
        message="Dados atualizados com sucesso",
        start_datetime=start_datetime,
        end_datetime=now,
        total_generated=total_generated,
    )


@router.post("/update-all-until-now", response_model=SimulatorUpdateAllResponse)
def update_all_until_now(payload: SimulatorUpdateAllRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rooms = db.scalars(select(Room).where(Room.is_deleted.is_(False)).order_by(Room.id).with_for_update()).all()
    latest = dict(db.execute(select(
        SensorReading.room_id, func.max(SensorReading.created_at),
    ).where(SensorReading.room_id.in_([room.id for room in rooms])).group_by(SensorReading.room_id)).all())
    plans, results = [], []
    for room in rooms:
        last = latest.get(room.id)
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        start = last + timedelta(seconds=payload.frequency_seconds) if last else now - timedelta(hours=DEFAULT_EMPTY_DATABASE_LOOKBACK_HOURS)
        if (last is not None and now - last < timedelta(seconds=UPDATE_COOLDOWN_SECONDS)) or start >= now:
            results.append(SimulatorRoomUpdate(room_id=room.id, name=room.name,
                message="Sala já atualizada", start_datetime=last, end_datetime=now))
            continue
        total = calculate_total_records(start, now, payload.frequency_seconds)
        ensure_generation_limit(total)
        plans.append((room, start, total))
    total_generated = sum(total for _, _, total in plans)
    ensure_generation_limit(total_generated)
    try:
        for room, start, total in plans:
            generate_simulated_readings(db, SimulatorGenerateRequest(
                device_id=room.device_id, location=room.location,
                start_datetime=start, end_datetime=now,
                frequency_seconds=payload.frequency_seconds, profile=payload.profile,
            ), commit=False)
            results.append(SimulatorRoomUpdate(room_id=room.id, name=room.name,
                message="Sala atualizada", start_datetime=start, end_datetime=now, total_generated=total))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return SimulatorUpdateAllResponse(
        message="Dados atualizados com sucesso" if plans else "Todas as salas já estão atualizadas" if rooms else "Nenhuma sala cadastrada",
        total_rooms=len(rooms), updated_rooms=len(plans), total_generated=total_generated, rooms=results,
    )
