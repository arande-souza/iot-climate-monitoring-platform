from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.room import Room
from app.models.sensor_reading import SensorReading


def get_room(db: Session, room_id: str) -> Room:
    room = db.get(Room, room_id)
    if room is None or room.is_deleted:
        raise HTTPException(status_code=404, detail="Sala nao encontrada")
    return room


def ensure_device_room(db: Session, device_id: str, location: str, data_source="unknown") -> Room:
    room = db.scalar(select(Room).where(Room.device_id == device_id))
    if room is not None:
        if room.is_deleted:
            raise HTTPException(status_code=409, detail="Dispositivo pertence a uma sala excluida")
        return room
    previous_room_id = db.scalar(select(SensorReading.room_id).where(
        SensorReading.device_id == device_id, SensorReading.room_id.is_not(None),
    ).limit(1))
    if previous_room_id:
        raise HTTPException(status_code=409, detail="Dispositivo substituido ou sala excluida; use o dispositivo atualmente associado")
    room = Room(name=location, location=location, device_id=device_id, data_source=data_source)
    try:
        with db.begin_nested():
            db.add(room)
            db.flush()
    except IntegrityError:
        # A simultaneous MQTT/API message may have registered the same device.
        room = db.scalar(select(Room).where(Room.device_id == device_id))
        if room is None:
            raise
        if room.is_deleted:
            raise HTTPException(status_code=409, detail="Dispositivo pertence a uma sala excluida")
    return room
