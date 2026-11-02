"""Additive, versioned migration for databases created before room management."""
from uuid import uuid4

from sqlalchemy import inspect, select, text

from app.database import Base, engine
from app.models.room import Room, SchemaMigration
from app.models.sensor_reading import SensorReading
from app.models.cost_scenario import CostScenario


def initialize_storage():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(2026102801)"))
        cost_columns = {column["name"] for column in inspect(connection).get_columns("cost_scenarios")}
        for name, sql_type in [("maintenance_cost", "NUMERIC(16, 2)"), ("maintenance_interval_months", "INTEGER")]:
            if name not in cost_columns:
                connection.execute(text(f"ALTER TABLE cost_scenarios ADD COLUMN {name} {sql_type}"))
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == "cost_maintenance_v1")):
            connection.execute(SchemaMigration.__table__.insert().values(version="cost_maintenance_v1"))
        room_columns = {column["name"] for column in inspect(connection).get_columns("rooms")}
        for name, size in [("identifier", 80), ("city", 120), ("state", 2), ("internal_location", 120)]:
            if name not in room_columns:
                connection.execute(text(
                    f"ALTER TABLE rooms ADD COLUMN {name} VARCHAR({size}) NOT NULL DEFAULT ''"
                ))
        if not connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == "room_locations_v2")):
            connection.execute(SchemaMigration.__table__.insert().values(version="room_locations_v2"))
        columns = {column["name"] for column in inspect(connection).get_columns("sensor_readings")}
        if "room_id" not in columns:
            connection.execute(text("ALTER TABLE sensor_readings ADD COLUMN room_id VARCHAR(36)"))
        if "data_source" not in columns:
            connection.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN data_source VARCHAR(20) NOT NULL DEFAULT 'unknown'"
            ))
        if connection.dialect.name == "postgresql":
            foreign_keys = inspect(connection).get_foreign_keys("sensor_readings")
            if not any(key["constrained_columns"] == ["room_id"] for key in foreign_keys):
                connection.execute(text(
                    "ALTER TABLE sensor_readings ADD CONSTRAINT fk_sensor_readings_room "
                    "FOREIGN KEY (room_id) REFERENCES rooms(id)"
                ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sensor_readings_room_created ON sensor_readings (room_id, created_at)"
        ))
        version = "rooms_v1"
        if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == version)):
            return
        devices = connection.execute(text(
            "SELECT DISTINCT device_id FROM sensor_readings"
        )).scalars().all()
        defaults = {"esp32-sala-01": ("Sala 1", "Santo André - SP"), "esp32-sala-02": ("Sala 2", "Sala 2")}
        for device_id in dict.fromkeys([*defaults, *devices]):
            location = connection.scalar(text(
                "SELECT location FROM sensor_readings WHERE device_id = :device ORDER BY created_at DESC, id DESC LIMIT 1"
            ), {"device": device_id})
            name, default_location = defaults.get(device_id, (location or device_id, location or device_id))
            room_id = connection.scalar(select(Room.id).where(Room.device_id == device_id))
            if room_id is None:
                room_id = str(uuid4())
                connection.execute(Room.__table__.insert().values(
                    id=room_id, name=name, location=location or default_location,
                    device_id=device_id, description="", temperature_min=20, temperature_max=26,
                    humidity_min=30, humidity_max=65,
                    data_source="simulation" if device_id in defaults else "unknown", source_config={}, is_deleted=False,
                ))
            connection.execute(text(
                "UPDATE sensor_readings SET room_id = :room WHERE device_id = :device AND room_id IS NULL"
            ), {"room": room_id, "device": device_id})
        connection.execute(SchemaMigration.__table__.insert().values(version=version))
