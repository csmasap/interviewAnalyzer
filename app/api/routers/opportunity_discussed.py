from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Body, status

from app.deps import (
    get_opportunity_service,
    get_agent_service,
    get_fit_agent_service,
    get_jobspy_service,
    get_workflow_service,
    get_workflow_state_service,
)
from app.models.schemas import (
    OpportunityDiscussed,
    OpportunityAnalysisResponse,
    OpportunityAnalysisRequest,
    CareerWorkflowResponse,
    WorkflowStartResponse,
    CareerPathRequest,
    WorkflowStepResponse,
    WorkflowFinalResponse,
    CareerFitnessScore,
)
from app.services.opportunity_service import OpportunityDiscussedService
from app.services.agent_service import OpenAIAgentService
from app.services.fit_agent_service import OpenAIFitAgentService
from app.services.jobspy_service import JobSpyService
from app.services.workflow_service import CareerWorkflowService
from app.services.workflow_state_service import WorkflowStateService

router = APIRouter(prefix="/opportunity-discussed", tags=["opportunity-discussed"])
logger = logging.getLogger(__name__)


async def _generate_fitness_score(
    agent: OpenAIAgentService, 
    analysis: str, 
    fit_gaps: str, 
    career_path: str
) -> CareerFitnessScore:
    """Generate a 0-100 fitness score with reasoning for how well candidate fits their desired career path."""
    
    prompt = (
        "You are a realistic career assessor who gives honest scores based on market realities. "
        "Score how likely this candidate is to achieve their career goal within 2-3 years, considering:\n"
        "- Current experience level vs. target role requirements\n"
        "- Typical career progression timelines in the industry\n"
        "- Market competition and hiring standards\n"
        "- Skill gaps and time needed to bridge them\n\n"
        "SCORING GUIDELINES:\n"
        "90-100: Already qualified or 1 promotion away\n"
        "70-89: Realistic with 2-3 years focused development\n"
        "50-69: Possible but requires significant effort and luck\n"
        "30-49: Major career pivot needed, very challenging\n"
        "0-29: Unrealistic goal given current background\n\n"
        f"Current Analysis:\n{analysis}\n\n"
        f"Fit & Gaps Assessment:\n{fit_gaps}\n\n"
        f"Desired Career Path:\n{career_path}\n\n"
        "Be brutally honest. Don't inflate scores to be nice.\n"
        "Respond in this exact format:\n"
        "SCORE: [number 0-100]\n"
        "REASONING: [honest 1-2 sentence explanation]"
    )
    
    try:
        resp = await agent._client.chat.completions.create(
            model=agent._model,
            messages=[
                {"role": "system", "content": "You provide precise numerical assessments with clear reasoning."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        
        content = resp.choices[0].message.content or ""
        
        # Parse score and reasoning
        lines = content.strip().split('\n')
        score = 50  # default
        reasoning = "Assessment could not be completed"
        
        for line in lines:
            if line.startswith("SCORE:"):
                try:
                    score_text = line.replace("SCORE:", "").strip()
                    score = max(0, min(100, int(score_text)))  # Clamp between 0-100
                except ValueError:
                    pass
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()
        
        return CareerFitnessScore(score=score, reasoning=reasoning)
        
    except Exception as e:
        logger.warning("Failed to generate fitness score: %s", e)
        return CareerFitnessScore(
            score=50, 
            reasoning="Unable to assess fitness due to technical issue"
        )


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
    record = service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found",
        )
    return record


@router.get(
    "/{record_id}/analysis",
    response_model=OpportunityAnalysisResponse,
    summary="Analyze TR1__Opportunity_Discussed__c via OpenAI and return a recommendation plus fit/gaps",
)
async def analyze_opportunity_discussed(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    job_description: str | None = Query(default=None, description="Optional job description to evaluate fit"),
    service: OpportunityDiscussedService = Depends(get_opportunity_service),
    agent: OpenAIAgentService = Depends(get_agent_service),
    fit_agent: OpenAIFitAgentService = Depends(get_fit_agent_service),
) -> OpportunityAnalysisResponse:
    record = service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    try:
        analysis_text = await agent.analyze_opportunity(record, job_description=job_description)
        fit_text = await fit_agent.assess_fit(record, job_description=job_description)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return OpportunityAnalysisResponse(id=record.id, analysis=analysis_text, fit_and_gaps=fit_text)


@router.post(
    "/{record_id}/analysis",
    response_model=OpportunityAnalysisResponse,
    summary="Analyze TR1__Opportunity_Discussed__c via OpenAI with optional job description in the body (includes fit/gaps)",
)
async def analyze_opportunity_discussed_post(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    payload: OpportunityAnalysisRequest = Body(default=OpportunityAnalysisRequest()),
    service: OpportunityDiscussedService = Depends(get_opportunity_service),
    agent: OpenAIAgentService = Depends(get_agent_service),
    fit_agent: OpenAIFitAgentService = Depends(get_fit_agent_service),
) -> OpportunityAnalysisResponse:
    record = service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    try:
        analysis_text = await agent.analyze_opportunity(record, job_description=payload.job_description)
        fit_text = await fit_agent.assess_fit(record, job_description=payload.job_description)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return OpportunityAnalysisResponse(id=record.id, analysis=analysis_text, fit_and_gaps=fit_text)


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

    try:
        jobs = jobspy.search(record, override={k: v for k, v in override.items() if v is not None})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Job scraping failed: {e}")

    return jobs


@router.post(
    "/{record_id}/workflow",
    response_model=CareerWorkflowResponse,
    summary="Execute career workflow: analysis -> career path prompt -> guidance -> jobs",
)
async def execute_career_workflow(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    payload: OpportunityAnalysisRequest = Body(default=OpportunityAnalysisRequest()),
    service: OpportunityDiscussedService = Depends(get_opportunity_service),
    workflow: CareerWorkflowService = Depends(get_workflow_service),
) -> CareerWorkflowResponse:
    record = service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    # Collect workflow results with timeout protection
    workflow_data = {}
    
    try:
        # Add asyncio timeout wrapper
        async def run_workflow():
            async for step in workflow.execute_workflow(record, job_description=payload.job_description):
                yield step
        
        workflow_gen = run_workflow()
        
        async for step in workflow_gen:
            logger.info("Workflow step completed: %s", step.step_name)
            
            if step.step_name == "analysis_complete":
                workflow_data.update(step.data)
            elif step.step_name == "career_path_collected":
                workflow_data.update(step.data)
            elif step.step_name == "guidance_complete":
                workflow_data.update(step.data)
            elif step.step_name == "jobs_complete":
                workflow_data.update(step.data)
            elif step.step_name == "error":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Workflow failed: {step.data.get('error', 'Unknown error')}"
                )

        return CareerWorkflowResponse(
            id=record.id,
            analysis=workflow_data["analysis"],
            fit_and_gaps=workflow_data["fit_and_gaps"],
            career_path=workflow_data["career_path"],
            career_guidance=workflow_data["career_guidance"],
            recommended_jobs=workflow_data["jobs"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Workflow execution failed for record %s: %s", record_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {e}"
        )


# New sequential workflow endpoints
@router.post(
    "/{record_id}/workflow/start",
    response_model=WorkflowStartResponse,
    summary="Start career workflow - Step 1: Generate analysis and prompt for career path",
)
async def start_career_workflow(
    record_id: str = Path(
        ...,
        description="Salesforce Id (15–18 chars) of TR1__Opportunity_Discussed__c",
        min_length=15,
        max_length=18,
        pattern=r"^[A-Za-z0-9]{15,18}$",
    ),
    payload: OpportunityAnalysisRequest = Body(default=OpportunityAnalysisRequest()),
    opp_service: OpportunityDiscussedService = Depends(get_opportunity_service),
    agent: OpenAIAgentService = Depends(get_agent_service),
    fit_agent: OpenAIFitAgentService = Depends(get_fit_agent_service),
    state_service: WorkflowStateService = Depends(get_workflow_state_service),
) -> WorkflowStartResponse:
    # Get the record
    record = opp_service.get_by_id(record_id=record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    try:
        # Step 1: Generate analysis
        analysis_task = agent.analyze_opportunity(record, job_description=payload.job_description)
        fit_task = fit_agent.assess_fit(record, job_description=payload.job_description)
        
        analysis, fit_gaps = await asyncio.gather(analysis_task, fit_task)
        
        # Create workflow state
        workflow_state = state_service.create_workflow(record_id, payload.job_description)
        workflow_state.update_step("analysis_complete", {
            "analysis": analysis,
            "fit_and_gaps": fit_gaps
        })

        return WorkflowStartResponse(
            workflow_id=workflow_state.id,
            record_id=record_id,
            analysis=analysis,
            fit_and_gaps=fit_gaps,
            next_step="career_path",
            message="Analysis complete. Please provide your desired career path."
        )

    except Exception as e:
        logger.exception("Failed to start workflow for record %s: %s", record_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start workflow: {e}"
        )


@router.post(
    "/workflow/{workflow_id}/career-path",
    response_model=WorkflowStepResponse,
    summary="Submit career path - Step 2: Process career goals and generate guidance",
)
async def submit_career_path(
    workflow_id: str = Path(..., description="Workflow ID from start endpoint"),
    career_request: CareerPathRequest = Body(...),
    state_service: WorkflowStateService = Depends(get_workflow_state_service),
    agent: OpenAIAgentService = Depends(get_agent_service),
) -> WorkflowStepResponse:
    # Get workflow state
    workflow_state = state_service.get_workflow(workflow_id)
    if not workflow_state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found or expired")

    if workflow_state.current_step != "analysis_complete":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid step. Expected 'analysis_complete', got '{workflow_state.current_step}'"
        )

    try:
        # Generate career guidance
        analysis = workflow_state.data["analysis"]
        fit_gaps = workflow_state.data["fit_and_gaps"]
        
        prompt = (
            "You are a senior career advisor known for giving realistic, actionable advice. "
            "Based on the candidate's current state and their career goal, provide honest guidance.\n\n"
            "Your advice should:\n"
            "1. Be REALISTIC about timeline (don't promise quick fixes)\n"
            "2. Prioritize the MOST CRITICAL gaps first\n"
            "3. Include estimated TIMEFRAMES for development\n"
            "4. Mention if the goal is particularly challenging or unrealistic\n"
            "5. Suggest intermediate milestones if the goal is ambitious\n"
            "6. Be specific about skills, experience, certifications, or connections needed\n\n"
            "If someone with minimal experience wants a senior role at a top company, "
            "tell them honestly that it may take 5-10 years and suggest realistic stepping stones.\n\n"
            f"Current Analysis:\n{analysis}\n\n"
            f"Fit & Gaps Assessment:\n{fit_gaps}\n\n"
            f"Desired Career Path:\n{career_request.career_path}\n\n"
            "Provide honest, actionable career guidance with realistic timelines:"
        )

        resp = await agent._client.chat.completions.create(
            model=agent._model,
            messages=[
                {"role": "system", "content": "You are a precise, actionable career advisor."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        guidance = resp.choices[0].message.content or ""

        # Generate fitness score
        fitness_score = await _generate_fitness_score(
            agent, analysis, fit_gaps, career_request.career_path
        )

        # Update workflow state
        workflow_state.update_step("guidance_complete", {
            "career_path": career_request.career_path,
            "career_guidance": guidance
        })

        return WorkflowStepResponse(
            workflow_id=workflow_id,
            current_step="guidance_complete",
            completed=False,
            data={"career_guidance": guidance},
            next_step="jobs",
            message="Career guidance generated. Fetching relevant job recommendations...",
            fitness_score=fitness_score
        )

    except Exception as e:
        logger.exception("Failed to process career path for workflow %s: %s", workflow_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process career path: {e}"
        )


@router.post(
    "/workflow/{workflow_id}/complete",
    response_model=WorkflowFinalResponse,
    summary="Complete workflow - Step 3: Fetch jobs and return final results",
)
async def complete_workflow(
    workflow_id: str = Path(..., description="Workflow ID"),
    state_service: WorkflowStateService = Depends(get_workflow_state_service),
    opp_service: OpportunityDiscussedService = Depends(get_opportunity_service),
    jobspy: JobSpyService = Depends(get_jobspy_service),
) -> WorkflowFinalResponse:
    # Get workflow state
    workflow_state = state_service.get_workflow(workflow_id)
    if not workflow_state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found or expired")

    if workflow_state.current_step != "guidance_complete":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid step. Expected 'guidance_complete', got '{workflow_state.current_step}'"
        )

    try:
        # Get the record for job search
        record = opp_service.get_by_id(record_id=workflow_state.record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original record not found")

        # Fetch jobs (limited to 3)
        job_override = {"results_wanted": 3}
        try:
            jobs = jobspy.search(record, override=job_override)
            if not jobs:
                logger.warning("No jobs found for workflow %s", workflow_id)
                jobs = []
        except Exception as e:
            logger.warning("Job search failed for workflow %s: %s", workflow_id, e)
            jobs = []

        # Mark workflow complete
        workflow_state.update_step("completed", {"jobs": jobs})
        workflow_state.mark_completed()

        # Prepare final response
        response = WorkflowFinalResponse(
            workflow_id=workflow_id,
            record_id=workflow_state.record_id,
            analysis=workflow_state.data["analysis"],
            fit_and_gaps=workflow_state.data["fit_and_gaps"],
            career_path=workflow_state.data["career_path"],
            career_guidance=workflow_state.data["career_guidance"],
            recommended_jobs=jobs,
            completed=True
        )

        # Clean up workflow state (optional)
        state_service.cleanup_workflow(workflow_id)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to complete workflow %s: %s", workflow_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete workflow: {e}"
        )


@router.get(
    "/workflow/{workflow_id}/status",
    response_model=WorkflowStepResponse,
    summary="Get workflow status and current step",
)
async def get_workflow_status(
    workflow_id: str = Path(..., description="Workflow ID"),
    state_service: WorkflowStateService = Depends(get_workflow_state_service),
) -> WorkflowStepResponse:
    workflow_state = state_service.get_workflow(workflow_id)
    if not workflow_state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found or expired")

    next_step = None
    message = None
    
    if workflow_state.current_step == "analysis_complete":
        next_step = "career_path"
        message = "Ready for career path submission"
    elif workflow_state.current_step == "guidance_complete":
        next_step = "complete"
        message = "Ready to fetch jobs and complete workflow"
    elif workflow_state.completed:
        message = "Workflow completed successfully"

    return WorkflowStepResponse(
        workflow_id=workflow_id,
        current_step=workflow_state.current_step,
        completed=workflow_state.completed,
        data=workflow_state.data,
        next_step=next_step,
        message=message
    )
