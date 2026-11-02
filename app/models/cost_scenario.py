from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CostScenario(Base):
    __tablename__ = "cost_scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("rooms.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    equipment_model: Mapped[str] = mapped_column(String(160), nullable=False)
    cooling_capacity_btu_h: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    average_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    equipment_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    installation_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    maintenance_cost: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    maintenance_interval_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hours_per_day: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    days_per_month: Mapped[int] = mapped_column(Integer, nullable=False)
    tariff_per_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    label_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    label_reference_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    label_period: Mapped[str | None] = mapped_column(String(10), nullable=True)
    parameter_source: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
