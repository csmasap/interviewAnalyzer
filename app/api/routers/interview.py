from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Body, status

from app.deps import get_interview_service
from app.models.schemas import (
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewYesNoAnswers,
    InterviewOpenEndedResponse,
    InterviewCompleteRequest,
    InterviewCompleteResponse,
)
from app.services.interview_service import InterviewService

router = APIRouter(prefix="/interview", tags=["interview"])
logger = logging.getLogger(__name__)


@router.post(
    "/{record_id}/start",
    response_model=InterviewStartResponse,
    summary="Start an AI-powered interview for a candidate",
)
async def start_interview(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    payload: InterviewStartRequest = Body(...),
    interview_service: InterviewService = Depends(get_interview_service),
) -> InterviewStartResponse:
    """Start an interview by generating a position and three yes/no questions."""
    
    try:
        result = await interview_service.start_interview(record_id)
        
        return InterviewStartResponse(
            interview_id=result["interview_id"],
            record_id=result["record_id"],
            position_title=result["position_title"],
            yes_no_questions=result["yes_no_questions"],
            message=result["message"]
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to start interview for record %s: %s", record_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start interview: {e}"
        )


@router.post(
    "/{interview_id}/yes-no-answers",
    response_model=InterviewOpenEndedResponse,
    summary="Submit yes/no answers and get open-ended questions",
)
async def submit_yes_no_answers(
    interview_id: str = Path(..., description="Interview ID from start endpoint"),
    answers: InterviewYesNoAnswers = Body(...),
    interview_service: InterviewService = Depends(get_interview_service),
) -> InterviewOpenEndedResponse:
    """Submit yes/no answers and receive two open-ended questions."""
    
    try:
        result = await interview_service.submit_yes_no_answers(interview_id, answers.answers)
        
        return InterviewOpenEndedResponse(
            interview_id=result["interview_id"],
            yes_no_answers=result["yes_no_answers"],
            open_ended_questions=result["open_ended_questions"],
            message=result["message"]
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to submit yes/no answers for interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit answers: {e}"
        )


@router.post(
    "/{interview_id}/complete",
    response_model=InterviewCompleteResponse,
    summary="Complete the interview with open-ended answers",
)
async def complete_interview(
    interview_id: str = Path(..., description="Interview ID"),
    payload: InterviewCompleteRequest = Body(...),
    interview_service: InterviewService = Depends(get_interview_service),
) -> InterviewCompleteResponse:
    """Complete the interview and save results to Salesforce."""
    
    try:
        result = await interview_service.complete_interview(interview_id, payload.open_ended_answers)
        
        return InterviewCompleteResponse(
            interview_id=result["interview_id"],
            record_id=result["record_id"],
            summary=result["summary"],
            message=result["message"]
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to complete interview %s: %s", interview_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete interview: {e}"
        )


@router.get(
    "/{interview_id}/status",
    summary="Get interview status and current step",
)
async def get_interview_status(
    interview_id: str = Path(..., description="Interview ID"),
    interview_service: InterviewService = Depends(get_interview_service),
):
    """Get the current status of an interview session."""
    
    session = interview_service.get_interview_session(interview_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found"
        )
    
    return {
        "interview_id": interview_id,
        "record_id": session["record_id"],
        "position_title": session["position_title"],
        "current_step": session["step"],
        "completed": session["step"] == "completed",
        "has_yes_no_answers": session["yes_no_answers"] is not None,
        "has_open_ended_questions": session["open_ended_questions"] is not None,
        "has_summary": session["summary"] is not None
    }
