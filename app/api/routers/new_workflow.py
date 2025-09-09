from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Body, status

from app.deps import get_new_workflow_service
from app.services.new_workflow_service import NewWorkflowService

router = APIRouter(prefix="/new-workflow", tags=["new-workflow"])
logger = logging.getLogger(__name__)


@router.post(
    "/{record_id}/start",
    response_model=dict,
    summary="Start the new skill-based workflow for a candidate",
)
async def start_new_workflow(
    record_id: str = Path(
        ...,
        description="Salesforce Contact Id (003...) containing resume text",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    new_workflow_service: NewWorkflowService = Depends(get_new_workflow_service),
) -> dict:
    """Start the new workflow by extracting skills from resume."""
    try:
        result = await new_workflow_service.start_interview(record_id)
        return result
    except ValueError as e:
        logger.error(f"ValueError in start_new_workflow for record {record_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in start_new_workflow for record {record_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post(
    "/{interview_id}/generate-questions",
    response_model=dict,
    summary="Generate interview questions for the new workflow",
)
async def generate_questions(
    interview_id: str = Path(..., description="Interview ID from start endpoint"),
    new_workflow_service: NewWorkflowService = Depends(get_new_workflow_service),
) -> dict:
    """Generate 7 questions based on the extracted skills."""
    try:
        result = await new_workflow_service.generate_questions(interview_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to generate questions for new workflow interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {e}"
        )


@router.post(
    "/{interview_id}/answer",
    response_model=dict,
    summary="Submit answer to current question in the new workflow",
)
async def submit_answer(
    interview_id: str = Path(..., description="Interview ID"),
    answer: str = Body(..., description="Answer to the current question", min_length=1),
    new_workflow_service: NewWorkflowService = Depends(get_new_workflow_service),
) -> dict:
    """Submit answer and get next question or complete interview."""
    try:
        result = await new_workflow_service.submit_answer(interview_id, answer)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to submit answer for new workflow interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit answer: {e}"
        )