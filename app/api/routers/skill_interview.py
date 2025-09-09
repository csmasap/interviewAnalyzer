from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Body, status

from app.deps import get_skill_interview_service
from app.models.schemas import (
    InterviewStartRequest,
    InterviewStartResponse,
)
from app.services.skill_interview_service import SkillInterviewService

router = APIRouter(prefix="/skill-interview", tags=["skill-interview"])
logger = logging.getLogger(__name__)


@router.post(
    "/{record_id}/start",
    response_model=dict,
    summary="Start a skill-based interview for a candidate",
)
async def start_skill_interview(
    record_id: str = Path(
        ...,
        description="Salesforce Contact Id (003...) containing resume text",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    skill_interview_service: SkillInterviewService = Depends(get_skill_interview_service),
) -> dict:
    """Start a skill-based interview by extracting skills from resume."""

    try:
        result = await skill_interview_service.start_skill_interview(record_id)

        return {
            "interview_id": result["interview_id"],
            "record_id": result["record_id"],
            "skills": result["skills"],
            "message": result["message"]
        }

    except ValueError as e:
        logger.error(f"ValueError in start_skill_interview for record {record_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in start_skill_interview for record {record_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post(
    "/{interview_id}/generate-questions",
    response_model=dict,
    summary="Generate interview questions based on extracted skills",
)
async def generate_questions(
    interview_id: str = Path(..., description="Interview ID from start endpoint"),
    skill_interview_service: SkillInterviewService = Depends(get_skill_interview_service),
) -> dict:
    """Generate 7 questions based on the extracted skills."""

    try:
        result = await skill_interview_service.generate_questions(interview_id)

        return {
            "interview_id": result["interview_id"],
            "questions": result["questions"],
            "current_question": result["current_question"],
            "message": result["message"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to generate questions for interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {e}"
        )


@router.post(
    "/{interview_id}/answer",
    response_model=dict,
    summary="Submit answer to current question",
)
async def submit_answer(
    interview_id: str = Path(..., description="Interview ID"),
    answer: str = Body(..., description="Answer to the current question", min_length=1),
    skill_interview_service: SkillInterviewService = Depends(get_skill_interview_service),
) -> dict:
    """Submit answer to current question and get next question or complete interview."""

    try:
        result = await skill_interview_service.submit_answer(interview_id, answer)

        return {
            "interview_id": result["interview_id"],
            "completed": result["completed"],
            "next_question": result.get("next_question"),
            "question_number": result.get("question_number"),
            "total_questions": result.get("total_questions"),
            "transcript": result.get("transcript"),
            "message": result["message"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to submit answer for interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit answer: {e}"
        )


@router.get(
    "/{interview_id}/status",
    summary="Get skill interview status and current step",
)
async def get_skill_interview_status(
    interview_id: str = Path(..., description="Interview ID"),
    skill_interview_service: SkillInterviewService = Depends(get_skill_interview_service),
):
    """Get the current status of a skill interview session."""

    try:
        result = await skill_interview_service.get_interview_status(interview_id)

        return {
            "interview_id": interview_id,
            "step": result["step"],
            "current_question_index": result["current_question_index"],
            "total_questions": result["total_questions"],
            "skills": result["skills"],
            "completed": result["completed"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to get status for interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get interview status: {e}"
        )