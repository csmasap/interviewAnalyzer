"""
THEIA Agent Coordination Service
Coordinates the execution of ISA agents for interview preparation.
Implements parallel execution of ISA_Researcher and ISA_Detector, followed by ISA_Questioner.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from theia_agents.isa_researcher import ISAResearcher
from theia_agents.isa_detector import ISADetector
from theia_agents.isa_questioner import ISAQuestioner
from models import (
    ResearchOutput,
    SkillsDetectionOutput,
    QuestionGenerationOutput,
    PreparedInterviewContext,
)

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Coordinates the execution of THEIA agents for interview preparation.
    
    Execution Flow:
    1. Start ISA_Researcher and ISA_Detector in parallel
    2. Wait for both to complete
    3. Feed both outputs to ISA_Questioner
    4. Return comprehensive preparation data
    """
    
    def __init__(self):
        """Initialize the Agent Coordinator"""
        self.researcher = None
        self.detector = None
        self.questioner = None
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize all agents"""
        try:
            self.researcher = ISAResearcher()
            logger.info("✅ ISA_Researcher initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ISA_Researcher: {e}")
            self.researcher = None
            
        try:
            self.detector = ISADetector()
            logger.info("✅ ISA_Detector initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ISA_Detector: {e}")
            self.detector = None
            
        try:
            self.questioner = ISAQuestioner()
            logger.info("✅ ISA_Questioner initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ISA_Questioner: {e}")
            self.questioner = None
    
    async def prepare_interview_data(
        self,
        company_name: str,
        job_title: str,
        job_description: str,
        candidate_resume: str,
        session_id: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Prepare comprehensive interview data using parallel agent execution.
        
        Args:
            company_name: Company name for research
            job_title: Job title/position
            job_description: Complete job description
            candidate_resume: Candidate's resume text
            session_id: Session identifier for tracking
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dict containing all agent outputs and generated questions
        """
        logger.info(f"🚀 Starting parallel agent coordination for session {session_id}")
        logger.info(f"📊 Company: {company_name}, Role: {job_title}")
        logger.info(f"📄 Resume: {len(candidate_resume)} chars, JD: {len(job_description)} chars")
        
        start_time = datetime.utcnow()
        
        # Update progress: Starting preparation
        if progress_callback:
            await progress_callback("Initializing interview preparation agents...", 10)
        
        # Phase 1: Run ISA_Researcher and ISA_Detector in parallel
        logger.info("🔄 Phase 1: Starting parallel execution of ISA_Researcher and ISA_Detector")
        
        if progress_callback:
            await progress_callback("Researching company and analyzing job requirements...", 25)
        
        # Create parallel tasks
        research_task = None
        skills_task = None
        
        if self.researcher:
            research_task = asyncio.create_task(
                self._run_researcher(company_name, job_title, job_description),
                name=f"researcher_{session_id}"
            )
            logger.info("🔍 ISA_Researcher task started")
        
        if self.detector:
            skills_task = asyncio.create_task(
                self._run_detector(job_description, job_title, company_name),
                name=f"detector_{session_id}"
            )
            logger.info("🎯 ISA_Detector task started")
        
        # Wait for both parallel tasks to complete
        research_output = None
        skills_output = None
        
        if research_task and skills_task:
            # Both agents available - run in parallel
            try:
                logger.info("⏳ Waiting for parallel agent execution to complete...")
                research_output, skills_output = await asyncio.gather(
                    research_task, skills_task, return_exceptions=True
                )
                
                # Handle exceptions
                if isinstance(research_output, Exception):
                    logger.error(f"❌ ISA_Researcher failed: {research_output}")
                    research_output = None
                    
                if isinstance(skills_output, Exception):
                    logger.error(f"❌ ISA_Detector failed: {skills_output}")
                    skills_output = None
                    
                logger.info("✅ Parallel agent execution completed")
                
            except Exception as e:
                logger.error(f"❌ Parallel execution failed: {e}")
                research_output = None
                skills_output = None
        else:
            # Fallback: run sequentially if one agent is missing
            if research_task:
                try:
                    research_output = await research_task
                except Exception as e:
                    logger.error(f"❌ ISA_Researcher failed: {e}")
                    research_output = None
                    
            if skills_task:
                try:
                    skills_output = await skills_task
                except Exception as e:
                    logger.error(f"❌ ISA_Detector failed: {e}")
                    skills_output = None
        
        # Update progress: Phase 1 complete
        phase1_time = datetime.utcnow()
        phase1_duration = (phase1_time - start_time).total_seconds()
        logger.info(f"⏱️ Phase 1 completed in {phase1_duration:.2f} seconds")
        
        if progress_callback:
            await progress_callback("Generating personalized interview questions...", 70)
        
        # Phase 2: Run ISA_Questioner with outputs from Phase 1
        logger.info("🔄 Phase 2: Starting ISA_Questioner with parallel outputs")
        
        questions_output = None
        if self.questioner:
            try:
                questions_output = await self._run_questioner(
                    job_description, job_title, company_name, candidate_resume,
                    research_output, skills_output
                )
                logger.info(f"✅ ISA_Questioner completed - {len(questions_output.questions) if questions_output else 0} questions generated")
            except Exception as e:
                logger.error(f"❌ ISA_Questioner failed: {e}")
                questions_output = None
        
        # Calculate total execution time
        end_time = datetime.utcnow()
        total_duration = (end_time - start_time).total_seconds()
        logger.info(f"⏱️ Total agent coordination completed in {total_duration:.2f} seconds")
        
        # Update progress: Complete
        if progress_callback:
            await progress_callback("Interview preparation complete!", 100)
        
        # Build normalized prepared context for downstream agents (text/voice)
        prepared_context = self._build_prepared_context(
            session_id=session_id,
            company_name=company_name,
            job_title=job_title,
            interview_mode=None,
            job_description=job_description,
            candidate_resume=candidate_resume,
            research_output=research_output,
            skills_output=skills_output,
            questions_output=questions_output,
        )

        # Prepare comprehensive response
        result = {
            "session_id": session_id,
            "status": "completed",
            "execution_time": total_duration,
            "phase1_time": phase1_duration,
            "parallel_execution": research_task is not None and skills_task is not None,
            "agents_executed": {
                "isa_researcher": research_output is not None,
                "isa_detector": skills_output is not None,
                "isa_questioner": questions_output is not None
            },
            "research_output": research_output.dict() if research_output else None,
            "skills_output": skills_output.dict() if skills_output else None,
            "questions_output": questions_output.dict() if questions_output else None,
            "questions": self._format_questions_for_frontend(questions_output) if questions_output else [],
            "company_name": company_name,
            "job_title": job_title,
            "timestamp": end_time.isoformat(),
            "prepared_context": prepared_context.dict() if prepared_context else None,
        }
        # Emit a generic completion payload for downstream consumers (ISA Chat/Voice)
        try:
            from websocket.manager import websocket_manager
            await websocket_manager.publish_message(
                channel="theia_websocket_messages",
                message={
                    "type": "session_message",
                    "session_id": session_id,
                    "data": {
                        "type": "preparation_complete",
                        "session_id": session_id,
                        "prepared": True,
                        "prepared_context": result["prepared_context"],
                        "company_name": company_name,
                        "job_title": job_title,
                        "questions": result.get("questions", []),
                        "timestamp": result.get("timestamp"),
                    },
                },
            )
            logger.info(f"📣 Published preparation_complete event for session {session_id}")
        except Exception as pub_err:
            logger.warning(f"⚠️ Could not publish preparation_complete event: {pub_err}")
        
        logger.info(f"🎉 Agent coordination completed successfully for session {session_id}")
        logger.info(f"📊 Results: Research={bool(research_output)}, Skills={bool(skills_output)}, Questions={len(result['questions'])}")
        
        return result
    
    async def _run_researcher(
        self, 
        company_name: str, 
        job_title: str, 
        job_description: str
    ) -> Optional[ResearchOutput]:
        """Run ISA_Researcher with error handling"""
        try:
            logger.info(f"🔍 ISA_Researcher: Starting research for {company_name}")
            result = await self.researcher.research_company_interview_practices(
                company_name=company_name,
                job_title=job_title,
                job_description=job_description
            )
            logger.info(f"✅ ISA_Researcher: Research completed for {company_name}")
            return result
        except Exception as e:
            logger.error(f"❌ ISA_Researcher execution failed: {e}")
            raise e
    
    async def _run_detector(
        self,
        job_description: str,
        job_title: str,
        company_name: str
    ) -> Optional[SkillsDetectionOutput]:
        """Run ISA_Detector with error handling"""
        try:
            logger.info(f"🎯 ISA_Detector: Starting skills analysis for {job_title}")
            result = await self.detector.analyze_job_requirements(
                job_description=job_description,
                job_title=job_title,
                company_name=company_name
            )
            logger.info(f"✅ ISA_Detector: Skills analysis completed - {len(result.key_skills) if result else 0} skills detected")
            return result
        except Exception as e:
            logger.error(f"❌ ISA_Detector execution failed: {e}")
            raise e
    
    async def _run_questioner(
        self,
        job_description: str,
        job_title: str,
        company_name: str,
        candidate_resume: str,
        research_output: Optional[ResearchOutput],
        skills_output: Optional[SkillsDetectionOutput]
    ) -> Optional[QuestionGenerationOutput]:
        """Run ISA_Questioner with outputs from parallel agents"""
        try:
            logger.info(f"❓ ISA_Questioner: Starting question generation")
            logger.info(f"📊 Inputs: Research={bool(research_output)}, Skills={bool(skills_output)}, Resume={len(candidate_resume)} chars")
            
            result = await self.questioner.generate_interview_questions(
                job_description=job_description,
                job_title=job_title,
                company_name=company_name,
                candidate_resume=candidate_resume,
                research_output=research_output,
                skills_output=skills_output
            )
            
            logger.info(f"✅ ISA_Questioner: Question generation completed")
            return result
        except Exception as e:
            logger.error(f"❌ ISA_Questioner execution failed: {e}")
            raise e
    
    def _format_questions_for_frontend(self, questions_output: QuestionGenerationOutput) -> list:
        """Format questions for frontend consumption"""
        if not questions_output or not questions_output.questions:
            return []
        
        return [
            {"id": f"q{i+1}", "text": question}
            for i, question in enumerate(questions_output.questions)
        ]
    
    def _build_prepared_context(
        self,
        *,
        session_id: str,
        company_name: str,
        job_title: str,
        interview_mode: Optional[str],
        job_description: str,
        candidate_resume: Optional[str],
        research_output: Optional[ResearchOutput],
        skills_output: Optional[SkillsDetectionOutput],
        questions_output: Optional[QuestionGenerationOutput],
    ) -> PreparedInterviewContext:
        """Create a stable, consumption-oriented context for downstream agents.

        This function is intentionally defensive: all fields are defaulted so
        agents can rely on presence without fragile optional chaining.
        """
        key_skills = []
        competencies = []
        technical_requirements = []
        soft_skills = []
        experience_level = None
        scorecard_criteria = {}

        if skills_output:
            try:
                key_skills = list(skills_output.key_skills or [])
                competencies = list(skills_output.competencies or [])
                technical_requirements = list(skills_output.technical_requirements or [])
                soft_skills = list(skills_output.soft_skills or [])
                experience_level = skills_output.experience_level or None
                scorecard_criteria = dict(skills_output.scorecard_criteria or {})
            except Exception:
                pass

        interview_overview = None
        interview_style = None
        common_questions = []
        market_intelligence = {}
        sources = []

        if research_output:
            try:
                # Company information may contain overview; be robust to schema
                ci = dict(research_output.company_info or {})
                interview_overview = (
                    ci.get("interview_overview")
                    or ci.get("overview")
                    or (research_output.interview_insights[0] if research_output.interview_insights else None)
                )
                interview_style = research_output.interview_style or ci.get("interview_style")
                common_questions = list(research_output.common_questions or [])
                market_intelligence = dict(research_output.market_intelligence or {})
                sources = list(research_output.sources_found or [])
            except Exception:
                pass

        questions = []
        question_rationale = []
        difficulty_levels = []
        question_types = []
        skill_coverage = {}
        if questions_output:
            try:
                questions = list(questions_output.questions or [])
                question_rationale = list(questions_output.question_rationale or [])
                difficulty_levels = list(questions_output.difficulty_levels or [])
                question_types = list(questions_output.question_types or [])
                skill_coverage = dict(questions_output.skill_coverage or {})
            except Exception:
                pass

        return PreparedInterviewContext(
            session_id=session_id,
            company_name=company_name,
            job_title=job_title,
            interview_mode=interview_mode,
            job_description=job_description,
            candidate_resume=candidate_resume or None,
            key_skills=key_skills,
            competencies=competencies,
            technical_requirements=technical_requirements,
            soft_skills=soft_skills,
            experience_level=experience_level,
            scorecard_criteria=scorecard_criteria,
            interview_overview=interview_overview,
            interview_style=interview_style,
            common_questions=common_questions,
            market_intelligence=market_intelligence,
            sources=sources,
            questions=questions,
            question_rationale=question_rationale,
            difficulty_levels=difficulty_levels,
            question_types=question_types,
            skill_coverage=skill_coverage,
        )
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents"""
        return {
            "coordinator_status": "active",
            "agents": {
                "isa_researcher": {
                    "initialized": self.researcher is not None,
                    "status": "active" if self.researcher else "inactive"
                },
                "isa_detector": {
                    "initialized": self.detector is not None,
                    "status": "active" if self.detector else "inactive"
                },
                "isa_questioner": {
                    "initialized": self.questioner is not None,
                    "status": "active" if self.questioner else "inactive"
                }
            },
            "parallel_execution_supported": self.researcher is not None and self.detector is not None,
            "timestamp": datetime.utcnow().isoformat()
        }


# Global coordinator instance
_coordinator_instance = None

def get_agent_coordinator() -> AgentCoordinator:
    """Get the global agent coordinator instance"""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = AgentCoordinator()
    return _coordinator_instance
