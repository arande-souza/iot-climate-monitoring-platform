from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.room import Room
from app.models.sensor_reading import SensorReading
from app.schemas.room_schema import RoomCreate, RoomResponse
from app.schemas.sensor_reading_schema import SensorReadingResponse
from app.services.room_service import get_room
from app.services.room_analytics_service import (
    ALERTS, consolidated_history, history_series, overview, period, room_snapshot, source_counts, statistics,
)

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomResponse])
def list_rooms(db: Session = Depends(get_db)):
    return db.scalars(select(Room).where(Room.is_deleted.is_(False)).order_by(Room.name, Room.id)).all()


def save_room(db, room, payload):
    previous_owner = db.scalar(select(SensorReading.room_id).where(
        SensorReading.device_id == payload.device_id,
        SensorReading.room_id.is_not(None),
        SensorReading.room_id != room.id if room.id else SensorReading.room_id.is_not(None),
    ).limit(1))
    if previous_owner:
        raise HTTPException(409, "Dispositivo possui historico associado a outra sala")
    for field, value in payload.model_dump(mode="json", exclude_unset=bool(room.id)).items():
        setattr(room, field, value)
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dispositivo ja vinculado a outra sala, inclusive salas excluidas")
    db.refresh(room)
    return room


@router.post("", response_model=RoomResponse, status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    return save_room(db, Room(), payload)


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    return overview(db)


@router.get("/comparison")
def get_comparison(
    start: datetime | None = None, end: datetime | None = None,
    days: int = Query(1, ge=1, le=365), db: Session = Depends(get_db),
):
    start, end = period(start, end, days)
    rooms = db.scalars(select(Room).where(Room.is_deleted.is_(False)).order_by(Room.name, Room.id)).all()
    stats = statistics(db, [room.id for room in rooms], start, end)
    return {"start": start, "end": end, "rooms": [
        {"room": RoomResponse.model_validate(room), "statistics": stats.get(room.id),
         "sources": source_counts(db, room.id, start, end)} for room in rooms
    ]}


@router.get("/overview/history")
def get_overview_history(
    start: datetime | None = None, end: datetime | None = None,
    days: int = Query(1, ge=1, le=365), room_id: str | None = None,
    db: Session = Depends(get_db),
):
    if room_id:
        get_room(db, room_id)
    start, end = period(start, end, days)
    return consolidated_history(db, start, end, room_id)


@router.get("/{room_id}", response_model=RoomResponse)
def read_room(room_id: str, db: Session = Depends(get_db)):
    return get_room(db, room_id)


@router.put("/{room_id}", response_model=RoomResponse)
def update_room(room_id: str, payload: RoomCreate, db: Session = Depends(get_db)):
    room = get_room(db, room_id)
    return save_room(db, room, payload)


@router.delete("/{room_id}", status_code=204)
def delete_room(room_id: str, confirm: bool = False, db: Session = Depends(get_db)):
    room = get_room(db, room_id)
    if not confirm:
        raise HTTPException(400, "Confirme a exclusao com confirm=true")
    room.is_deleted = True
    db.commit()
    return Response(status_code=204)


@router.get("/{room_id}/dashboard")
def get_room_dashboard(
    room_id: str, start: datetime | None = None, end: datetime | None = None,
    days: int = Query(1, ge=1, le=365), db: Session = Depends(get_db),
):
    room = get_room(db, room_id)
    start, end = period(start, end, days)
    series, bucket_seconds = history_series(db, room.id, start, end)
    alerts = db.scalars(select(SensorReading).where(
        SensorReading.room_id == room.id, SensorReading.created_at >= start,
        SensorReading.created_at <= end, SensorReading.air_quality_status.in_(ALERTS),
    ).order_by(SensorReading.created_at.desc(), SensorReading.id.desc()).limit(20)).all()
    return {
        **room_snapshot(db, room), "start": start, "end": end,
        "statistics": statistics(db, [room.id], start, end).get(room.id),
        "series": series, "bucket_seconds": bucket_seconds,
        "sources": source_counts(db, room.id, start, end),
        "alerts": [SensorReadingResponse.model_validate(row) for row in alerts],
    }
