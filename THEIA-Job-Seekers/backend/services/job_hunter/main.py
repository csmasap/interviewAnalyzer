from __future__ import annotations

import logging
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.job_hunter.api.routers import api_router

app = FastAPI(
    title="Interview Analyzer API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(api_router)

# CORS: allow THEIA frontend during local dev and typical prod origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

from services.job_hunter.core.config import get_settings
from services.job_hunter.core.logging_config import configure_logging


configure_logging("INFO")
logger = logging.getLogger(__name__)

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
