from uuid import uuid4

from sqlalchemy import Boolean, Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    device_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    identifier: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    state: Mapped[str] = mapped_column(String(2), default="", server_default="", nullable=False)
    internal_location: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    temperature_min: Mapped[float] = mapped_column(Float, default=20, nullable=False)
    temperature_max: Mapped[float] = mapped_column(Float, default=26, nullable=False)
    humidity_min: Mapped[float] = mapped_column(Float, default=30, nullable=False)
    humidity_max: Mapped[float] = mapped_column(Float, default=65, nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    source_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String(80), primary_key=True)
