from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Body, status

from app.deps import get_job_analyzer_service
from app.models.schemas import JobAnalysisRequest, JobAnalysisResponse
from app.services.job_analyzer_service import JobAnalyzerService

router = APIRouter(prefix="/job-analyzer", tags=["job-analyzer"])
logger = logging.getLogger(__name__)


@router.post(
    "/generate-questions",
    response_model=JobAnalysisResponse,
    summary="Generate 3 interview questions based on job description",
)
async def generate_interview_questions(
    request: JobAnalysisRequest = Body(...),
    analyzer: JobAnalyzerService = Depends(get_job_analyzer_service),
) -> JobAnalysisResponse:
    """Generate targeted interview questions from a job description."""
    
    if not request.job_description.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job description cannot be empty"
        )
    
    if len(request.job_description.strip()) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job description must be at least 50 characters long"
        )
    
    try:
        questions = await analyzer.generate_interview_questions(request.job_description)
        return JobAnalysisResponse(questions=questions)
        
    except Exception as e:
        logger.exception("Failed to generate interview questions: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate interview questions. Please try again."
        )
