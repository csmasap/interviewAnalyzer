from __future__ import annotations

import logging
from typing import Dict

from fastapi import FastAPI, Request

from app.api.routers import api_router

app = FastAPI(
    title="Interview Analyzer API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(api_router)

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.deps import get_salesforce_client


configure_logging("INFO")
logger = logging.getLogger(__name__)

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
    # Create TR1__Application__c record in Salesforce when page is loaded
    application_record_id = None
    application_status = None
    try:
        sf_client = get_salesforce_client()

        # Check if record already exists
        existing_record_id = sf_client.query_application_record_exists(
            applicant_id=record_id,
            job_id='a0WPM0000045Kjl2AE'
        )

        if existing_record_id:
            application_record_id = existing_record_id
            application_status = "existing"
            logger.info("Found existing TR1__Application__c record for super view: %s", application_record_id)
        else:
            # Create new record
            application_record_id = sf_client.create_application_record(
                applicant_id=record_id,
                job_id='a0WPM0000045Kjl2AE',
                source='ASAP Website'
            )
            application_status = "created"
            logger.info("Created new TR1__Application__c record for super view: %s", application_record_id)

    except Exception as e:
        logger.warning("Failed to handle TR1__Application__c record for super view, but continuing to serve page: %s", e)
        # Don't fail the page load if Salesforce operations fail

    return templates.TemplateResponse("super_view.html", {
        "request": request,
        "record_id": record_id,
        "application_record_id": application_record_id,
        "application_status": application_status
    })


@app.get("/workflow", response_class=HTMLResponse, tags=["ui"])
async def workflow_ui(request: Request, record_id: str = "a0N123456789012"):
    """Serve the workflow UI page"""
    return templates.TemplateResponse("workflow.html", {"request": request, "record_id": record_id})


@app.get("/job-analyzer", response_class=HTMLResponse, tags=["ui"])
async def job_analyzer_ui(request: Request):
    """Serve the job analyzer UI page"""
    return templates.TemplateResponse("job_analyzer.html", {"request": request})


@app.get("/interview", response_class=HTMLResponse, tags=["ui"])
async def interview_ui(request: Request, record_id: str = "a0N123456789012", application_record_id: str = None):
    """Serve the interview UI page"""
    return templates.TemplateResponse("interview.html", {
        "request": request,
        "record_id": record_id,
        "application_record_id": application_record_id
    })


@app.get("/new-workflow", response_class=HTMLResponse, tags=["ui"])
async def new_workflow_ui(request: Request, record_id: str = "003123456789012345"):
    """Serve the new workflow UI page"""
    return templates.TemplateResponse("new_workflow.html", {
        "request": request,
        "record_id": record_id
    })
@app.get("/skill-interview", response_class=HTMLResponse, tags=["ui"])
async def skill_interview_ui(request: Request, record_id: str = "003123456789012345"):
    """Serve the skill interview UI page"""
    return templates.TemplateResponse("skill_interview.html", {
        "request": request,
        "record_id": record_id
    })
