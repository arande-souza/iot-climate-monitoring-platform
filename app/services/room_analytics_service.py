from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import Integer, case, cast, extract, func, select

from app.models.room import Room
from app.models.sensor_reading import SensorReading as Reading
from app.schemas.room_schema import RoomResponse
from app.schemas.sensor_reading_schema import SensorReadingResponse
from app.services.classification_service import classify_environment

ALERTS = ("alerta", "critico", "alert", "critical")
STALE_AFTER_MINUTES = 30


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def period(start=None, end=None, days=1):
    now = datetime.now(timezone.utc)
    end = aware(end) if end else now
    start = aware(start) if start else end - timedelta(days=days)
    start, end = start.astimezone(timezone.utc), min(end.astimezone(timezone.utc), now)
    if start >= end:
        raise HTTPException(422, "A data inicial deve ser anterior a data final e ao momento atual")
    return start, end


def valid_conditions():
    return [Reading.temperature.between(-40, 85), Reading.humidity.between(0, 100)]


def room_snapshot(db, room):
    now = datetime.now(timezone.utc)
    latest = db.scalar(select(Reading).where(
        Reading.room_id == room.id, Reading.created_at <= now, *valid_conditions(),
    ).order_by(Reading.created_at.desc(), Reading.id.desc()).limit(1))
    stale = latest is not None and now - aware(latest.created_at) > timedelta(minutes=STALE_AFTER_MINUTES)
    status = classify_environment(latest, room) if latest else "sem_dados"
    return {
        "room": RoomResponse.model_validate(room),
        "latest_reading": SensorReadingResponse.model_validate(latest) if latest else None,
        "status": status, "stale": stale,
        "monitoring_status": "sem_dados" if latest is None else "desatualizado" if stale else {
            "ideal": "normal", "aceitavel": "normal", "alerta": "atencao", "critico": "critico",
        }[status],
    }


def overview(db):
    rooms = db.scalars(select(Room).where(Room.is_deleted.is_(False)).order_by(Room.name, Room.id)).all()
    snapshots = [room_snapshot(db, room) for room in rooms]
    current = [item["latest_reading"] for item in snapshots
               if item["latest_reading"] and not item["stale"]
               and item["latest_reading"].data_source != "external_api"]
    counts = {status: sum(item["monitoring_status"] == status for item in snapshots)
              for status in ("normal", "atencao", "critico", "sem_dados", "desatualizado")}
    return {
        "total_rooms": len(rooms), "counts": counts, "rooms": snapshots,
        "temperature_avg": sum(item.temperature for item in current) / len(current) if current else None,
        "humidity_avg": sum(item.humidity for item in current) / len(current) if current else None,
        "valid_rooms": len(current), "updated_at": datetime.now(timezone.utc),
        "average_sources": {source: sum(item.data_source == source for item in current)
                            for source in ("sensor", "simulation", "unknown")},
        "external_reference_rooms": sum(item["latest_reading"] is not None
                                        and item["latest_reading"].data_source == "external_api"
                                        for item in snapshots),
        "stale_after_minutes": STALE_AFTER_MINUTES,
        "connectivity_available": False,
        "active_devices": None,
    }


def time_bucket(db, seconds):
    epoch = extract("epoch", Reading.created_at) if db.bind.dialect.name == "postgresql" else cast(
        func.strftime("%s", Reading.created_at), Integer,
    )
    return func.floor(epoch / seconds)


def consolidated_history(db, start, end, room_id=None):
    """Average each room first so faster-reporting devices do not dominate other rooms."""
    seconds = max(60, int((end - start).total_seconds() / 360) + 1)
    bucket = time_bucket(db, seconds)
    conditions = [
        Room.is_deleted.is_(False), Reading.created_at >= start, Reading.created_at <= end,
        Reading.data_source != "external_api", *valid_conditions(),
    ]
    if room_id:
        conditions.append(Reading.room_id == room_id)
    per_room = select(
        bucket.label("bucket"), Reading.room_id,
        func.min(Reading.created_at).label("at"),
        func.avg(Reading.temperature).label("temperature"),
        func.avg(Reading.humidity).label("humidity"),
        func.count().label("count"),
        func.sum(case((Reading.air_quality_status.in_(("alerta", "alert")), 1), else_=0)).label("alerts"),
        func.sum(case((Reading.air_quality_status.in_(("critico", "critical")), 1), else_=0)).label("critical"),
    ).join(Room, Room.id == Reading.room_id).where(*conditions).group_by(bucket, Reading.room_id).subquery()
    rows = db.execute(select(
        func.min(per_room.c.at).label("at"),
        func.avg(per_room.c.temperature).label("temperature"),
        func.avg(per_room.c.humidity).label("humidity"),
        func.sum(per_room.c.count).label("count"), func.count().label("room_count"),
        func.sum(per_room.c.alerts).label("alerts"), func.sum(per_room.c.critical).label("critical"),
    ).group_by(per_room.c.bucket).order_by(per_room.c.bucket)).mappings()
    series = [{**dict(row), "at": aware(row["at"])} for row in rows]
    sources = dict(db.execute(select(Reading.data_source, func.count()).join(
        Room, Room.id == Reading.room_id,
    ).where(*conditions).group_by(Reading.data_source)).all())
    return {"start": start, "end": end, "room_id": room_id, "series": series,
            "bucket_seconds": seconds, "sources": sources,
            "averaging": "equal_weight_per_room_per_bucket"}


def statistics(db, room_ids, start, end):
    stmt = select(
        Reading.room_id, func.count().label("count"),
        func.min(Reading.temperature).label("temperature_min"),
        func.max(Reading.temperature).label("temperature_max"),
        func.avg(Reading.temperature).label("temperature_avg"),
        func.min(Reading.humidity).label("humidity_min"),
        func.max(Reading.humidity).label("humidity_max"),
        func.avg(Reading.humidity).label("humidity_avg"),
        func.sum(case((Reading.air_quality_status.in_(ALERTS), 1), else_=0)).label("alerts"),
    ).where(
        Reading.room_id.in_(room_ids), Reading.created_at >= start, Reading.created_at <= end,
        *valid_conditions(),
    ).group_by(Reading.room_id)
    return {row["room_id"]: dict(row) for row in db.execute(stmt).mappings()}


def history_series(db, room_id, start, end):
    # At most about 360 buckets; aggregate every measurement instead of truncating history.
    seconds = max(60, int((end - start).total_seconds() / 360) + 1)
    bucket = time_bucket(db, seconds)
    stmt = select(
        func.min(Reading.created_at).label("at"),
        func.avg(Reading.temperature).label("temperature"),
        func.avg(Reading.humidity).label("humidity"), func.count().label("count"),
    ).where(
        Reading.room_id == room_id, Reading.created_at >= start, Reading.created_at <= end,
        *valid_conditions(),
    ).group_by(bucket).order_by(bucket)
    points = [{**dict(row), "at": aware(row["at"])} for row in db.execute(stmt).mappings()]
    return points, seconds


def source_counts(db, room_id, start, end):
    return dict(db.execute(select(Reading.data_source, func.count()).where(
        Reading.room_id == room_id, Reading.created_at >= start, Reading.created_at <= end,
        *valid_conditions(),
    ).group_by(Reading.data_source)).all())
