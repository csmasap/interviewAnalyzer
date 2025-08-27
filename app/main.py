from __future__ import annotations

import logging
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.routers import api_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging


configure_logging("INFO")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Interview Analyzer API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting application in environment=%s", settings.environment)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down application")


@app.get("/healthz", tags=["health"])
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def super_view(request: Request, record_id: str = "a0N123456789012"):
    """Serve the super view dashboard for all services"""
    return templates.TemplateResponse("super_view.html", {"request": request, "record_id": record_id})


@app.get("/workflow", response_class=HTMLResponse, tags=["ui"])
async def workflow_ui(request: Request, record_id: str = "a0N123456789012"):
    """Serve the workflow UI page"""
    return templates.TemplateResponse("workflow.html", {"request": request, "record_id": record_id})


@app.get("/job-analyzer", response_class=HTMLResponse, tags=["ui"])
async def job_analyzer_ui(request: Request):
    """Serve the job analyzer UI page"""
    return templates.TemplateResponse("job_analyzer.html", {"request": request})


@app.get("/interview", response_class=HTMLResponse, tags=["ui"])
async def interview_ui(request: Request, record_id: str = "a0N123456789012"):
    """Serve the interview UI page"""
    return templates.TemplateResponse("interview.html", {"request": request, "record_id": record_id})


app.include_router(api_router)
