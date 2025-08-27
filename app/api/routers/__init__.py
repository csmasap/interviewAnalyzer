from fastapi import APIRouter

from .opportunity_discussed import router as opportunity_discussed_router
from .job_analyzer import router as job_analyzer_router
from .interview import router as interview_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(opportunity_discussed_router)
api_router.include_router(job_analyzer_router)
api_router.include_router(interview_router)

__all__ = [
    "api_router",
]
