import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import Base, engine
from app.routes.sensor_routes import router as sensor_router
from app.routes.simulator_routes import router as simulator_router
from app.services.mqtt_service import start_mqtt_service, stop_mqtt_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_mqtt_service()
    logger.info("Application started")
    try:
        yield
    finally:
        stop_mqtt_service()
        logger.info("Application stopped")


app = FastAPI(
    title="IoT Climate Monitoring Platform",
    description="API e dashboard para monitoramento climático em ambientes tecnológicos.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(sensor_router)
app.include_router(simulator_router)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
def health_check():
    return {"status": "ok"}
