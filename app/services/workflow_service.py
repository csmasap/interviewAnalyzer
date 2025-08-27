from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from app.models.schemas import OpportunityDiscussed
from app.services.agent_service import OpenAIAgentService
from app.services.fit_agent_service import OpenAIFitAgentService
from app.services.jobspy_service import JobSpyService

logger = logging.getLogger(__name__)


class WorkflowStep:
    def __init__(self, step_name: str, data: Any) -> None:
        self.step_name = step_name
        self.data = data


class CareerWorkflowService:
    def __init__(
        self,
        agent_service: OpenAIAgentService,
        fit_agent_service: OpenAIFitAgentService,
        jobspy_service: JobSpyService,
    ) -> None:
        self._agent = agent_service
        self._fit_agent = fit_agent_service
        self._jobspy = jobspy_service

    async def _generate_career_guidance(self, analysis: str, fit_gaps: str, career_path: str) -> str:
        """Use OpenAI to compare analysis with desired career path and provide guidance."""
        prompt = (
            "You are a senior career advisor. You have an analysis of a candidate and their desired career path. "
            "Provide specific, actionable guidance on what they need to work on to achieve their goal. "
            "Be concrete about skills, experience, certifications, or projects they should pursue.\n\n"
            f"Current Analysis:\n{analysis}\n\n"
            f"Fit & Gaps Assessment:\n{fit_gaps}\n\n"
            f"Desired Career Path:\n{career_path}\n\n"
            "Provide career guidance:"
        )

        resp = await self._agent._client.chat.completions.create(
            model=self._agent._model,
            messages=[
                {"role": "system", "content": "You are a precise, actionable career advisor."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        return resp.choices[0].message.content or ""

    def _prompt_career_path(self) -> str:
        """Simple terminal prompt for career path. In production, this could be a web form or API."""
        print("\n" + "="*60)
        print("CAREER WORKFLOW: Tell us about your desired career path")
        print("="*60)
        career_path = input("What is your desired career path? (Be specific): ").strip()
        if not career_path:
            career_path = "Continue growing in my current field"
        logger.info("User provided career path: %s", career_path)
        return career_path

    async def execute_workflow(self, record: OpportunityDiscussed, job_description: Optional[str] = None) -> AsyncGenerator[WorkflowStep, None]:
        """
        Execute the complete career workflow:
        1. Generate analysis + fit/gaps
        2. Prompt for career path
        3. Generate career guidance
        4. Fetch relevant jobs
        """
        try:
            # Step 1: Generate analysis
            logger.info("Workflow Step 1: Generating analysis for record %s", record.id)
            analysis_task = self._agent.analyze_opportunity(record, job_description)
            fit_task = self._fit_agent.assess_fit(record, job_description)
            
            analysis, fit_gaps = await asyncio.gather(analysis_task, fit_task)
            
            yield WorkflowStep("analysis_complete", {
                "analysis": analysis,
                "fit_and_gaps": fit_gaps
            })

            # Step 2: Prompt for career path (synchronous terminal interaction)
            logger.info("Workflow Step 2: Prompting for career path")
            career_path = self._prompt_career_path()
            
            yield WorkflowStep("career_path_collected", {
                "career_path": career_path
            })

            # Step 3: Generate career guidance
            logger.info("Workflow Step 3: Generating career guidance")
            guidance = await self._generate_career_guidance(analysis, fit_gaps, career_path)
            
            yield WorkflowStep("guidance_complete", {
                "career_guidance": guidance
            })

            # Step 4: Fetch relevant jobs (limited to 3, with timeout protection)
            logger.info("Workflow Step 4: Fetching relevant jobs")
            job_override = {"results_wanted": 3}
            try:
                jobs = self._jobspy.search(record, override=job_override)
                if not jobs:
                    logger.warning("No jobs found, using empty list")
                    jobs = []
            except Exception as e:
                logger.warning("Job search failed, continuing with empty list: %s", e)
                jobs = []
            
            yield WorkflowStep("jobs_complete", {
                "jobs": jobs
            })

            logger.info("Workflow completed successfully for record %s", record.id)

        except Exception as e:
            logger.exception("Workflow failed for record %s: %s", record.id, e)
            yield WorkflowStep("error", {
                "error": str(e),
                "record_id": record.id
            })
