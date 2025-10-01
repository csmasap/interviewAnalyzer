from fastapi import APIRouter

from .opportunity_discussed import router as opportunity_discussed_router
from .sample_jobs import router as sample_jobs_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(opportunity_discussed_router)
api_router.include_router(sample_jobs_router)

__all__ = [
    "api_router"
]
