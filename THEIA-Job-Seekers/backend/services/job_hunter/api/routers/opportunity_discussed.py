from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from services.job_hunter.deps import (
    get_opportunity_service,
    get_jobspy_service,
)
from services.job_hunter.models.schemas import (
    OpportunityDiscussed,
)
from services.job_hunter.services.opportunity_service import OpportunityDiscussedService
from services.job_hunter.services.jobspy_service import JobSpyService

router = APIRouter(prefix="/opportunity-discussed", tags=["opportunity-discussed"])
logger = logging.getLogger(__name__)




@router.get(
    "/{record_id}",
    response_model=OpportunityDiscussed,
    summary="Get TR1__Opportunity_Discussed__c by Id",
)
async def get_opportunity_discussed(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    service: OpportunityDiscussedService = Depends(get_opportunity_service),
) -> OpportunityDiscussed:
    logger.info("Stage 1: Fetching OpportunityDiscussed record id=%s", record_id)
    record = service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found",
        )
    logger.info(
        "Stage 1: Record loaded (candidate=%s)",
        "yes" if record.candidate is not None else "no",
    )
    return record


# Analysis and workflow endpoints removed as part of pruning


# (POST) analysis endpoint removed


@router.get(
    "/{record_id}/jobs",
    response_model=list[dict],
    summary="Search jobs on LinkedIn/Indeed using JobSpy derived from the Salesforce record",
)
async def search_jobs(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    # Optional overrides for debugging/tuning
    search_term: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    results_wanted: Optional[int] = Query(default=None, ge=1, le=200),
    hours_old: Optional[int] = Query(default=None, ge=1, le=720),
    use_ai_query: Optional[bool] = Query(default=None, description="Use AI to build Boolean query from resume/interview"),
    service: OpportunityDiscussedService = Depends(get_opportunity_service),
    jobspy: JobSpyService = Depends(get_jobspy_service),
) -> List[Dict[str, Any]]:
    record = service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    override: Dict[str, Any] = {
        "search_term": search_term,
        "location": location,
        "results_wanted": results_wanted,
        "hours_old": hours_old,
    }

    if use_ai_query:
        try:
            logger.info("Stage 2: Generating AI-powered search query")
            from services.job_hunter.services.google_pse_service import build_ai_query
            ai = await build_ai_query(
                record.candidate.resume_text if (record.candidate and record.candidate.resume_text) else None,
                record.ai_interview_summary,
                None,
            )
            if ai.get("query"):
                override["search_term"] = ai["query"]
            if ai.get("location"):
                override["location"] = ai["location"]
            if ai.get("country_code"):
                override["country_indeed"] = str(ai["country_code"]).upper()
            logger.info(
                "Stage 2: AI query built (len=%s, location=%s, country=%s)",
                len(ai.get("query", "")),
                ai.get("location") or "",
                (ai.get("country_code") or "").upper(),
            )
        except Exception as e:
            logger.warning("Stage 2: AI query generation failed: %s", e)

    try:
        logger.info("Stage 3: Executing job search")
        jobs = jobspy.search(record, override={k: v for k, v in override.items() if v is not None})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Job scraping failed: {e}")

    logger.info("Stage 4: Search complete (jobs=%d)", len(jobs))
    return jobs


# Workflow endpoints removed


# Workflow status endpoint removed
