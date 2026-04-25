from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.sensor_reading import SensorReading
from app.schemas.sensor_reading_schema import (
    EnvironmentStatus,
    CriticalHourCount,
    PaginatedSensorReadings,
    SensorReadingCreate,
    SensorReadingResponse,
    ReadingsDateRange,
    ReadingsSummary,
)
from app.services.classification_service import (
    build_recommendations,
    classify_environment,
)

router = APIRouter(prefix="/api/readings", tags=["sensor readings"])
ALLOWED_PAGE_SIZES = {20, 50, 100, 200, 500, 1000}
ALERT_STATUS_VALUES = {
    "ideal": ("ideal", "normal"),
    "aceitavel": ("aceitavel", "acceptable"),
    "alerta": ("alerta", "alert"),
    "critico": ("critico", "critical"),
}


def create_sensor_reading(db: Session, payload: SensorReadingCreate) -> SensorReading:
    reading = SensorReading(
        **payload.model_dump(),
        air_quality_status=classify_environment(payload),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def validate_page_size(page_size: int) -> None:
    if page_size not in ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page_size deve ser 20, 50, 100, 200, 500 ou 1000",
        )


def paginate_readings(
    db: Session,
    stmt,
    count_stmt,
    page: int,
    page_size: int,
) -> PaginatedSensorReadings:
    validate_page_size(page_size)
    total = db.scalar(count_stmt) or 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    offset = (current_page - 1) * page_size
    items = db.scalars(stmt.offset(offset).limit(page_size)).all()
    return PaginatedSensorReadings(
        items=items,
        total=total,
        page=current_page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_alert_status_filter(alert_type: str | None) -> tuple[str, ...]:
    if alert_type is None or alert_type == "":
        return ("alerta", "critico", "alert", "critical")
    if alert_type not in ALERT_STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="alert_type deve ser alerta ou critico",
        )
    return ALERT_STATUS_VALUES[alert_type]


def get_reading_status_filter(reading_status: str | None) -> tuple[str, ...] | None:
    if reading_status is None or reading_status == "":
        return None
    if reading_status not in ALERT_STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status_filter deve ser ideal, aceitavel, alerta ou critico",
        )
    return ALERT_STATUS_VALUES[reading_status]


def parse_optional_datetime(value: str | None, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            normalized_value = value.rsplit(" ", 1)
            if len(normalized_value) == 2:
                return datetime.fromisoformat("+".join(normalized_value))
        except ValueError:
            pass
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"{field_name} deve estar em formato ISO 8601",
    )


@router.post(
    "",
    response_model=SensorReadingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reading(payload: SensorReadingCreate, db: Session = Depends(get_db)):
    return create_sensor_reading(db, payload)


@router.get("/latest", response_model=list[SensorReadingResponse])
def list_latest_readings(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(SensorReading).order_by(SensorReading.created_at.desc()).limit(limit)
    return db.scalars(stmt).all()


@router.get("/history", response_model=PaginatedSensorReadings)
def get_history(
    start: str | None = Query(default=None, description="Data inicial em ISO 8601"),
    end: str | None = Query(default=None, description="Data final em ISO 8601"),
    device_id: str | None = Query(default=None),
    status_filter: str | None = Query(
        default=None,
        description="Status da leitura: ideal, aceitavel, alerta ou critico",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50),
    db: Session = Depends(get_db),
):
    start_datetime = parse_optional_datetime(start, "start")
    end_datetime = parse_optional_datetime(end, "end")
    if start_datetime and end_datetime and start_datetime > end_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start deve ser anterior ou igual a end",
        )

    conditions = []
    if start_datetime:
        conditions.append(SensorReading.created_at >= start_datetime)
    if end_datetime:
        conditions.append(SensorReading.created_at <= end_datetime)
    if device_id:
        conditions.append(SensorReading.device_id == device_id)
    status_values = get_reading_status_filter(status_filter)
    if status_values:
        conditions.append(SensorReading.air_quality_status.in_(status_values))

    stmt = select(SensorReading).where(*conditions).order_by(SensorReading.created_at.asc())
    count_stmt = select(func.count()).select_from(SensorReading).where(*conditions)
    return paginate_readings(db, stmt, count_stmt, page, page_size)


@router.get("/range", response_model=ReadingsDateRange)
def get_readings_date_range(
    device_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(
        func.min(SensorReading.created_at),
        func.max(SensorReading.created_at),
    )
    if device_id:
        stmt = stmt.where(SensorReading.device_id == device_id)

    start_datetime, end_datetime = db.execute(stmt).one()
    return ReadingsDateRange(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )


@router.get("/summary", response_model=ReadingsSummary)
def get_readings_summary(db: Session = Depends(get_db)):
    total_readings = db.scalar(select(func.count()).select_from(SensorReading)) or 0
    return ReadingsSummary(total_readings=total_readings)


@router.get("/alerts", response_model=PaginatedSensorReadings)
def get_alert_history(
    start: str | None = Query(default=None, description="Data inicial em ISO 8601"),
    end: str | None = Query(default=None, description="Data final em ISO 8601"),
    device_id: str | None = Query(default=None),
    alert_type: str | None = Query(default=None, description="Tipo do alerta: alerta ou critico"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50),
    db: Session = Depends(get_db),
):
    start_datetime = parse_optional_datetime(start, "start")
    end_datetime = parse_optional_datetime(end, "end")
    if start_datetime and end_datetime and start_datetime > end_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start deve ser anterior ou igual a end",
        )

    conditions = [
        SensorReading.air_quality_status.in_(get_alert_status_filter(alert_type)),
    ]
    if start_datetime:
        conditions.append(SensorReading.created_at >= start_datetime)
    if end_datetime:
        conditions.append(SensorReading.created_at <= end_datetime)
    if device_id:
        conditions.append(SensorReading.device_id == device_id)

    stmt = select(SensorReading).where(*conditions).order_by(SensorReading.created_at.asc())
    count_stmt = select(func.count()).select_from(SensorReading).where(*conditions)
    return paginate_readings(db, stmt, count_stmt, page, page_size)


@router.get("/alerts/critical-hours", response_model=list[CriticalHourCount])
def get_critical_hours(
    start: str | None = Query(default=None, description="Data inicial em ISO 8601"),
    end: str | None = Query(default=None, description="Data final em ISO 8601"),
    device_id: str | None = Query(default=None),
    alert_type: str | None = Query(default=None, description="Tipo do alerta: alerta ou critico"),
    db: Session = Depends(get_db),
):
    start_datetime = parse_optional_datetime(start, "start")
    end_datetime = parse_optional_datetime(end, "end")
    if start_datetime and end_datetime and start_datetime > end_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start deve ser anterior ou igual a end",
        )

    conditions = [
        SensorReading.air_quality_status.in_(get_alert_status_filter(alert_type)),
    ]
    if start_datetime:
        conditions.append(SensorReading.created_at >= start_datetime)
    if end_datetime:
        conditions.append(SensorReading.created_at <= end_datetime)
    if device_id:
        conditions.append(SensorReading.device_id == device_id)

    if db.bind and db.bind.dialect.name == "postgresql":
        chart_datetime = func.timezone("America/Sao_Paulo", SensorReading.created_at)
    else:
        chart_datetime = SensorReading.created_at
    hour_expr = extract("hour", chart_datetime).label("hour")
    stmt = (
        select(
            hour_expr,
            SensorReading.air_quality_status,
            func.count().label("total"),
        )
        .where(*conditions)
        .group_by(hour_expr, SensorReading.air_quality_status)
        .order_by(hour_expr, SensorReading.air_quality_status)
    )
    totals_by_hour = {
        hour: {"alerta": 0, "critico": 0}
        for hour in range(24)
    }
    for hour, status_value, total in db.execute(stmt).all():
        normalized_status = {
            "alert": "alerta",
            "critical": "critico",
        }.get(status_value, status_value)
        totals_by_hour[int(hour)][normalized_status] += total

    return [
        CriticalHourCount(
            hour=hour,
            alerta=counts["alerta"],
            critico=counts["critico"],
            total=counts["alerta"] + counts["critico"],
        )
        for hour, counts in totals_by_hour.items()
    ]


@router.get("/device/{device_id}", response_model=list[SensorReadingResponse])
def get_readings_by_device(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = (
        select(SensorReading)
        .where(SensorReading.device_id == device_id)
        .order_by(SensorReading.created_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


@router.get("/status", response_model=EnvironmentStatus)
def get_environment_status(db: Session = Depends(get_db)):
    stmt = select(SensorReading).order_by(SensorReading.created_at.desc()).limit(1)
    latest = db.scalars(stmt).first()
    if latest is None:
        return EnvironmentStatus(
            status="sem_dados",
            latest_reading=None,
            recommendations=["Nenhuma leitura registrada até o momento."],
        )
    return EnvironmentStatus(
        status=latest.air_quality_status,
        latest_reading=latest,
        recommendations=build_recommendations(latest.air_quality_status),
    )
