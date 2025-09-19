from fastapi import APIRouter

from .opportunity_discussed import router as opportunity_discussed_router
from .skill_interview import router as skill_interview_router
from .job_analyzer import router as job_analyzer_router
from .interview import router as interview_router
from .new_workflow import router as new_workflow_router
from .sample_jobs import router as sample_jobs_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(opportunity_discussed_router)
api_router.include_router(sample_jobs_router)
api_router.include_router(skill_interview_router)
api_router.include_router(job_analyzer_router)
api_router.include_router(interview_router)
api_router.include_router(new_workflow_router)

__all__ = [
    "api_router", "sample_jobs_router"
]
