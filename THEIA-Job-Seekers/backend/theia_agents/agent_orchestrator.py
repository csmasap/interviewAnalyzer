"""
Agent Orchestrator - Concurrent Agent Execution
Optimizes agent workflows by running compatible agents concurrently.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from .isa_detector import ISADetector
from .isa_researcher import ISAResearcher
from .isa_questioner import ISAQuestioner
from .isa_evaluator import ISAEvaluator
from .base_agent import run_agents_concurrently, create_agent_task

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import (
    SkillsDetectionOutput, 
    ResearchOutput, 
    QuestionGenerationOutput, 
    EvaluationOutput
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates multiple agents for optimal performance
    
    Key Features:
    - Concurrent execution of independent agents
    - Dependency-aware scheduling
    - Performance monitoring
    - Error handling and fallbacks
    """
    
    def __init__(self):
        """Initialize the agent orchestrator"""
        self.detector = ISADetector()
        self.researcher = ISAResearcher()
        self.questioner = ISAQuestioner()
        self.evaluator = ISAEvaluator()
        
        self.performance_stats = {
            "total_workflows": 0,
            "concurrent_executions": 0,
            "time_saved_seconds": 0.0,
            "average_workflow_time": 0.0
        }
    
    async def run_preparation_workflow(
        self,
        job_description: str,
        job_title: str,
        company_name: str,
        candidate_resume: str,
        industry: Optional[str] = None
    ) -> Tuple[SkillsDetectionOutput, ResearchOutput, QuestionGenerationOutput]:
        """
        Run the complete interview preparation workflow with optimizations
        
        Phase 1: Run ISA_Detector and ISA_Researcher concurrently (independent)
        Phase 2: Run ISA_Questioner with results from Phase 1
        
        Returns:
            Tuple of (skills_output, research_output, questions_output)
        """
        start_time = time.time()
        self.performance_stats["total_workflows"] += 1
        
        logger.info(f"🚀 Starting optimized preparation workflow for {job_title} at {company_name}")
        
        try:
            # Phase 1: Run independent agents concurrently
            logger.info("📊 Phase 1: Running ISA_Detector and ISA_Researcher concurrently...")
            
            phase1_tasks = [
                create_agent_task(
                    self.detector.analyze_job_requirements,
                    job_description, job_title, company_name, industry
                ),
                create_agent_task(
                    self.researcher.research_company_interview_practices,
                    company_name, job_title, job_description, industry
                )
            ]
            
            phase1_results = await run_agents_concurrently(phase1_tasks)
            
            # Handle results and exceptions
            skills_output = None
            research_output = None
            
            for i, result in enumerate(phase1_results):
                if isinstance(result, Exception):
                    agent_name = ["ISA_Detector", "ISA_Researcher"][i]
                    logger.error(f"❌ {agent_name} failed: {result}")
                    # Create fallback outputs
                    if i == 0:  # ISA_Detector failed
                        skills_output = self._create_fallback_skills_output(job_title)
                    else:  # ISA_Researcher failed
                        research_output = self._create_fallback_research_output(company_name)
                else:
                    if i == 0:
                        skills_output = result
                    else:
                        research_output = result
            
            phase1_time = time.time() - start_time
            logger.info(f"✅ Phase 1 completed in {phase1_time:.2f}s")
            
            # Phase 2: Run ISA_Questioner with Phase 1 results
            logger.info("📝 Phase 2: Running ISA_Questioner with combined context...")
            
            questions_output = await self.questioner.generate_interview_questions(
                job_description=job_description,
                job_title=job_title,
                company_name=company_name,
                candidate_resume=candidate_resume,
                research_output=research_output,
                skills_output=skills_output
            )
            
            total_time = time.time() - start_time
            
            # Update performance stats
            self.performance_stats["concurrent_executions"] += 1
            estimated_sequential_time = phase1_time * 2 + (total_time - phase1_time)  # Rough estimate
            time_saved = max(0, estimated_sequential_time - total_time)
            self.performance_stats["time_saved_seconds"] += time_saved
            
            self.performance_stats["average_workflow_time"] = (
                (self.performance_stats["average_workflow_time"] * (self.performance_stats["total_workflows"] - 1) + total_time) /
                self.performance_stats["total_workflows"]
            )
            
            logger.info(f"🎉 Preparation workflow completed in {total_time:.2f}s")
            logger.info(f"⚡ Estimated time saved: {time_saved:.2f}s through concurrent execution")
            
            return skills_output, research_output, questions_output
            
        except Exception as e:
            logger.error(f"❌ Preparation workflow failed: {e}")
            raise
    
    async def run_evaluation_workflow(
        self,
        questions: List[str],
        answers: List[str],
        job_title: str,
        company_name: str,
        job_description: str,
        candidate_resume: str,
        skills_output: Optional[SkillsDetectionOutput] = None,
        questions_output: Optional[QuestionGenerationOutput] = None,
        interview_transcript: Optional[List[Dict[str, Any]]] = None
    ) -> EvaluationOutput:
        """
        Run the interview evaluation workflow
        
        Note: Evaluation is typically run after the interview, so no concurrency opportunities
        """
        start_time = time.time()
        
        logger.info(f"📊 Starting evaluation workflow for {job_title} interview")
        
        try:
            evaluation_output = await self.evaluator.evaluate_interview_performance(
                questions=questions,
                answers=answers,
                job_title=job_title,
                company_name=company_name,
                job_description=job_description,
                candidate_resume=candidate_resume,
                skills_output=skills_output,
                questions_output=questions_output,
                interview_transcript=interview_transcript
            )
            
            total_time = time.time() - start_time
            logger.info(f"✅ Evaluation workflow completed in {total_time:.2f}s")
            
            return evaluation_output
            
        except Exception as e:
            logger.error(f"❌ Evaluation workflow failed: {e}")
            raise
    
    def _create_fallback_skills_output(self, job_title: str) -> SkillsDetectionOutput:
        """Create a basic fallback skills output when ISA_Detector fails"""
        return SkillsDetectionOutput(
            job_title=job_title,
            key_skills=["Communication", "Problem Solving", "Teamwork", "Adaptability", "Technical Skills"],
            technical_requirements=["Relevant experience", "Industry knowledge"],
            soft_skills=["Communication", "Collaboration", "Time Management"],
            experience_level="Mid-level",
            scorecard_criteria={
                "Communication": "Clear and effective communication skills",
                "Problem Solving": "Ability to analyze and solve complex problems",
                "Teamwork": "Collaborative approach to work",
                "Adaptability": "Flexibility in changing environments",
                "Technical Skills": "Job-relevant technical competencies"
            },
            industry_context="General industry requirements",
            remote_work_considerations="Standard remote work capabilities"
        )
    
    def _create_fallback_research_output(self, company_name: str) -> ResearchOutput:
        """Create a basic fallback research output when ISA_Researcher fails"""
        return ResearchOutput(
            company_name=company_name,
            culture_overview="Professional work environment focused on results and collaboration",
            work_environment="Standard corporate environment with focus on teamwork",
            growth_opportunities="Career development and advancement opportunities available",
            company_size_impact="Medium-sized company with structured processes",
            interview_insights=[
                "Be prepared to discuss your experience and achievements",
                "Show enthusiasm for the role and company",
                "Ask thoughtful questions about the position and team"
            ],
            common_questions=[
                "Tell me about yourself",
                "Why are you interested in this position?",
                "What are your strengths and weaknesses?",
                "Describe a challenging project you worked on"
            ],
            interview_style="Professional and structured interview process",
            market_intelligence={
                "salary_ranges": "Competitive market rates",
                "benefits_highlights": "Standard benefits package",
                "competition_analysis": "Competitive industry landscape",
                "hiring_trends": "Active hiring for key positions"
            },
            research_confidence=0.3,
            sources_found=["Fallback data - original research unavailable"]
        )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get orchestrator performance statistics"""
        agent_stats = {
            "detector": self.detector.get_performance_stats(),
            "researcher": self.researcher.get_performance_stats(),
            "questioner": self.questioner.get_performance_stats(),
            "evaluator": self.evaluator.get_performance_stats()
        }
        
        return {
            "orchestrator": self.performance_stats,
            "agents": agent_stats,
            "total_cache_hits": sum(stats.get("cache_hits", 0) for stats in agent_stats.values()),
            "total_flash_usage": sum(stats.get("flash_model_uses", 0) for stats in agent_stats.values()),
            "total_pro_usage": sum(stats.get("pro_model_uses", 0) for stats in agent_stats.values())
        }
    
    def clear_all_caches(self):
        """Clear all agent caches"""
        self.detector.clear_cache()
        self.researcher.clear_cache()
        self.questioner.clear_cache()
        self.evaluator.clear_cache()
        logger.info("🧹 All agent caches cleared")


# Global orchestrator instance
orchestrator = AgentOrchestrator()
