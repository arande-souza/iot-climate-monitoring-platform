import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import Base, engine
from app.routes.auth_routes import router as auth_router
from app.routes.sensor_routes import router as sensor_router
from app.routes.simulator_routes import router as simulator_router
from app.security.auth import require_jwt_middleware, verify_token
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
    description="API e dashboard para monitoramento climatico em ambientes tecnologicos.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.middleware("http")(require_jwt_middleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router)
app.include_router(sensor_router, dependencies=[Depends(verify_token)])
app.include_router(simulator_router, dependencies=[Depends(verify_token)])


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, username: str = Depends(verify_token)):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_alias(request: Request, username: str = Depends(verify_token)):
    return dashboard(request, username)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/openapi.json", include_in_schema=False)
def protected_openapi(username: str = Depends(verify_token)):
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )


@app.get("/docs", include_in_schema=False)
def protected_docs(username: str = Depends(verify_token)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - Docs",
    )
