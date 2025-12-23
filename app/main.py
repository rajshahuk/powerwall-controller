"""Main FastAPI application for Powerwall Controller."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.api import router as api_router
from app.config import config
from app.services.storage_service import storage_service
from app.services.monitoring_service import monitoring_service
from app.services.automation_service import automation_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    storage_service.initialize()
    automation_service.load_rules()
    yield
    # Shutdown
    if automation_service.is_running:
        await automation_service.stop()
    if monitoring_service.is_running:
        await monitoring_service.stop()
    await storage_service.flush_all()


app = FastAPI(
    title="Powerwall Controller",
    description="Web application for monitoring and controlling Tesla Powerwall 3",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Setup templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_path)

# Include API routes
app.include_router(api_router)


# Page routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/configuration", response_class=HTMLResponse)
async def configuration(request: Request):
    """Configuration page."""
    return templates.TemplateResponse("configuration.html", {"request": request})


@app.get("/automation", response_class=HTMLResponse)
async def automation(request: Request):
    """Automation page."""
    return templates.TemplateResponse("automation.html", {"request": request})


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    """History page."""
    return templates.TemplateResponse("history.html", {"request": request})


@app.get("/audit", response_class=HTMLResponse)
async def audit(request: Request):
    """Audit log page."""
    return templates.TemplateResponse("audit.html", {"request": request})


def run():
    """Run the application."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
