import json
import logging
import os
from threading import Lock

from dotenv import load_dotenv
from paho.mqtt import client as mqtt
from pydantic import ValidationError

from app.database import SessionLocal
from app.schemas.sensor_reading_schema import SensorReadingCreate

load_dotenv()

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "climate/readings")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_ENABLED = os.getenv("MQTT_ENABLED", "true").lower() == "true"

_client: mqtt.Client | None = None
_lock = Lock()


def _on_connect(client: mqtt.Client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        logger.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe(MQTT_TOPIC)
        logger.info("Subscribed to MQTT topic %s", MQTT_TOPIC)
    else:
        logger.error("MQTT connection failed with code %s", reason_code)


def _on_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    from app.routes.sensor_routes import create_sensor_reading

    raw_payload = message.payload.decode("utf-8", errors="replace")
    logger.info("MQTT message received on %s: %s", message.topic, raw_payload)

    try:
        data = json.loads(raw_payload)
        payload = SensorReadingCreate.model_validate(data)
    except json.JSONDecodeError:
        logger.exception("Invalid MQTT JSON payload")
        return
    except ValidationError:
        logger.exception("Invalid MQTT sensor payload")
        return

    db = SessionLocal()
    try:
        reading = create_sensor_reading(db, payload)
        logger.info("MQTT reading persisted with id=%s", reading.id)
    except Exception:
        logger.exception("Failed to persist MQTT reading")
    finally:
        db.close()


def start_mqtt_service() -> None:
    global _client

    if not MQTT_ENABLED:
        logger.info("MQTT service disabled by MQTT_ENABLED=false")
        return

    with _lock:
        if _client is not None:
            return

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if MQTT_USERNAME:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        client.on_connect = _on_connect
        client.on_message = _on_message

        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            _client = client
        except Exception:
            logger.exception("Could not start MQTT service")
            _client = None


def stop_mqtt_service() -> None:
    global _client

    with _lock:
        if _client is None:
            return
        _client.loop_stop()
        _client.disconnect()
        _client = None
