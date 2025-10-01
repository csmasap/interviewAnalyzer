"""
ISA_Questioner Agent - Dynamic Interview Question Generation
Google Vertex AI agent for generating tailored interview questions based on job requirements and research.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

import vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.preview.generative_models import grounding
from utils.json_utils import extract_first_balanced_json, try_parse_json
import json

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import QuestionGenerationOutput, ResearchOutput, SkillsDetectionOutput
from config import settings
from .base_agent import OptimizedAgent, TaskComplexity

logger = logging.getLogger(__name__)


class ISAQuestioner(OptimizedAgent):
    """
    ISA_Questioner Agent
    
    Generates 10 tailored interview questions by combining:
    - Job description and requirements
    - Candidate's resume and background
    - Company research from ISA_Researcher
    - Skills analysis from ISA_Detector
    
    Creates a comprehensive question set covering all critical competencies.
    """
    
    def __init__(self):
        """Initialize the ISA_Questioner agent with optimizations"""
        super().__init__("ISA_Questioner")
    
    async def generate_interview_questions(
        self,
        job_description: str,
        job_title: str,
        company_name: str,
        candidate_resume: str,
        research_output: Optional[ResearchOutput] = None,
        skills_output: Optional[SkillsDetectionOutput] = None
    ) -> QuestionGenerationOutput:
        """
        Generate 10 tailored interview questions
        
        Args:
            job_description: Complete job description
            job_title: Job title/position
            company_name: Company name
            candidate_resume: Candidate's resume text
            research_output: Company research from ISA_Researcher
            skills_output: Skills analysis from ISA_Detector
            
        Returns:
            QuestionGenerationOutput: 10 tailored questions with metadata
        """
        logger.info(f"🔍 Generating interview questions for {job_title} at {company_name}")
        
        try:
            # Create question generation prompt
            generation_prompt = self._create_question_generation_prompt(
                job_description, job_title, company_name, candidate_resume,
                research_output, skills_output
            )
            
            # Prefer grounded generation using web search
            try:
                generation_response = await self._generate_questions_with_web(generation_prompt)
            except Exception:
                generation_response = await self._generate_questions(generation_prompt)
            
            # Parse and structure the question output
            questions_output = self._parse_questions_response(generation_response, job_title)

            # Inject candidate name if available from research/company insights in resume header
            try:
                candidate_name = None
                # Simple heuristic: look for a name at the top of the resume
                first_line = (candidate_resume or '').splitlines()[0:1]
                if first_line and len(first_line[0].split()) <= 5:
                    candidate_name = first_line[0].strip()
                if candidate_name:
                    questions_output.questions = [
                        q.replace("Candidate", candidate_name).replace("[Candidate]", candidate_name)
                        for q in questions_output.questions
                    ]
            except Exception:
                pass
            
            logger.info(f"✅ Generated {len(questions_output.questions)} questions for {job_title}")
            return questions_output
            
        except Exception as e:
            logger.error(f"❌ Question generation failed for {job_title}: {e}")
            logger.error(f"❌ Company: {company_name}, Resume length: {len(candidate_resume) if candidate_resume else 0}")
            logger.error(f"❌ Research available: {research_output is not None}, Skills available: {skills_output is not None}")
            # Return fallback questions
            return self._create_fallback_questions(job_title, job_description, candidate_resume)
    
    def _create_question_generation_prompt(
        self,
        job_description: str,
        job_title: str,
        company_name: str,
        candidate_resume: str,
        research_output: Optional[ResearchOutput] = None,
        skills_output: Optional[SkillsDetectionOutput] = None
    ) -> str:
        """Create a comprehensive question generation prompt"""
        
        # Build context from research output
        research_context = ""
        if research_output:
            research_context = f"""
COMPANY RESEARCH INSIGHTS:
Company Culture: {research_output.company_info.get('culture_overview', 'N/A')}
Interview Style: {research_output.interview_style}
Common Questions at Company: {', '.join(research_output.common_questions[:3])}
Market Intelligence: {research_output.market_intelligence}
Research Confidence: {research_output.research_confidence}
"""
        
        # Build context from skills analysis
        skills_context = ""
        if skills_output:
            skills_context = f"""
KEY SKILLS TO ASSESS:
{chr(10).join([f"- {skill}" for skill in skills_output.key_skills])}

TECHNICAL REQUIREMENTS:
{chr(10).join([f"- {req}" for req in skills_output.technical_requirements])}

SOFT SKILLS FOCUS:
{chr(10).join([f"- {skill}" for skill in skills_output.soft_skills])}

EXPERIENCE LEVEL: {skills_output.experience_level}
"""
        
        prompt = f"""
You are ISA_Questioner, an expert interview question designer and talent assessment specialist.

QUESTION GENERATION TASK:
Create exactly 10 tailored interview questions for this candidate and role, combining job requirements, candidate background, company research, and skills analysis.

JOB DETAILS:
Position: {job_title}
Company: {company_name}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{candidate_resume}

{research_context}

{skills_context}

QUESTION GENERATION STRATEGY:
1. SKILL COVERAGE: Ensure all key skills are covered across the 10 questions
2. QUESTION VARIETY: Mix behavioral, situational, technical, and cultural fit questions
3. COMPANY ALIGNMENT: Incorporate company-specific insights and culture
4. CANDIDATE PERSONALIZATION: Reference candidate's background and experience
5. PROGRESSIVE DIFFICULTY: Start with easier questions, build complexity
6. COMPREHENSIVE ASSESSMENT: Cover technical, soft skills, and cultural fit

PERSONALIZATION REQUIREMENTS:
- Address the candidate by name if present at the top of the resume (first line)
- Anchor questions to specific experiences, employers, or achievements mentioned in the resume
- Where possible, weave in company context (values, interview style) from research

QUESTION TYPES TO INCLUDE:
- Behavioral questions (Tell me about a time...)
- Situational questions (How would you handle...)
- Technical questions (specific to role requirements)
- Cultural fit questions (based on company research)
- Experience-based questions (leveraging candidate's background)
- Problem-solving questions
- Leadership/teamwork questions (if applicable)

OUTPUT REQUIREMENTS:
Provide exactly 10 questions in JSON format with these fields:

{{
    "questions": [
        "Question 1: Opening/warm-up question referencing candidate's background",
        "Question 2: Key skill assessment question",
        "Question 3: Behavioral question for important competency",
        "Question 4: Technical/role-specific question",
        "Question 5: Situational/problem-solving question",
        "Question 6: Company culture/values alignment question",
        "Question 7: Experience-based question leveraging candidate's background",
        "Question 8: Advanced technical or strategic question",
        "Question 9: Teamwork/collaboration question",
        "Question 10: Future-focused/growth question"
    ],
    "question_rationale": [
        "Why question 1 was chosen and what it assesses",
        "Rationale for question 2 and its assessment purpose",
        "Explanation for question 3 and competency focus",
        "Technical assessment purpose for question 4",
        "Problem-solving evaluation goal for question 5",
        "Cultural fit assessment reason for question 6",
        "Experience validation purpose for question 7",
        "Advanced assessment goal for question 8",
        "Teamwork evaluation purpose for question 9",
        "Growth potential assessment for question 10"
    ],
    "difficulty_levels": [
        "Easy - Warm-up",
        "Medium - Core skill",
        "Medium - Behavioral",
        "Medium-Hard - Technical",
        "Hard - Problem-solving",
        "Medium - Cultural fit",
        "Medium - Experience",
        "Hard - Advanced",
        "Medium - Teamwork",
        "Medium - Future focus"
    ],
    "skill_coverage": {{
        "Key Skill 1": [1, 2, 7],
        "Key Skill 2": [3, 4, 8],
        "Key Skill 3": [5, 6, 9],
        "Communication": [1, 6, 9, 10],
        "Problem-solving": [4, 5, 8],
        "Cultural fit": [6, 9, 10]
    }},
    "question_types": [
        "Background/Experience",
        "Skill Assessment",
        "Behavioral",
        "Technical",
        "Situational",
        "Cultural Fit",
        "Experience Validation",
        "Advanced Technical",
        "Teamwork",
        "Growth/Vision"
    ]
}}

CRITICAL GUIDELINES:
- Generate exactly 10 unique, non-repetitive questions
- Each question should be specific and actionable
- Reference candidate's actual experience where relevant
- Incorporate company-specific insights from research
- Ensure comprehensive coverage of all key skills
- Make questions realistic for the experience level
- Balance challenging and approachable questions
- Include follow-up potential in question design
- Avoid generic or clichéd questions
- Make questions conversational and natural
 - Whenever possible, explicitly reference the candidate's prior role/company or project from the resume
 - Do not fabricate facts not present in resume or research

CRITICAL OUTPUT RULES:
- Return ONLY a single JSON object as shown above (no markdown, no backticks, no prose).
- The JSON must be valid (no trailing commas, correct quoting).
- Do not include any explanation before or after the JSON.

Generate 10 tailored interview questions now:
"""
        return prompt
    
    async def _generate_questions(self, prompt: str) -> str:
        """Generate questions using optimized Vertex AI model"""
        # Question generation requires moderate complexity for creativity and structure
        return await self.generate_optimized(
            prompt=prompt,
            complexity=TaskComplexity.MODERATE,  # Use pro model but with optimized params
            max_tokens=2200,  # tighter to reduce truncation and drift
            timeout=45,  # Reduced from 120s to 45s
            use_cache=False  # Don't cache questions - each should be unique
        )

    async def _generate_questions_with_web(self, prompt: str) -> str:
        """Generate questions using Gemini with Web Search tool for company-aligned grounding.
        Primary: Enterprise Web Search via google.generativeai; fallback: Vertex google_search; final: plain.
        """
        model: Optional[GenerativeModel] = self._select_model(TaskComplexity.MODERATE)
        if not model:
            raise Exception("ISA_Questioner: Vertex AI models not initialized")
        config = self._get_generation_config(TaskComplexity.MODERATE, max_tokens=3000)
        config["temperature"] = 0.25  # Slightly creative but stable

        response_text: Optional[str] = None
        # 1) Enterprise Web Search via google.generativeai
        try:
            genai = None
            types = None
            try:
                import google.generativeai as genai  # type: ignore
                from google.generativeai import types  # type: ignore
            except Exception:
                try:
                    from google import genai  # type: ignore
                    from google.genai import types  # type: ignore
                except Exception:
                    genai = None
                    types = None
            if genai and types and getattr(types, "EnterpriseWebSearch", None):
                api_key = os.getenv("GOOGLE_API_KEY", "").strip() or settings.GOOGLE_API_KEY
                if api_key:
                    try:
                        genai.configure(api_key=api_key)  # type: ignore
                    except Exception:
                        pass
                gm = genai.GenerativeModel(self.model_pro)  # type: ignore[attr-defined]
                cfg = types.GenerateContentConfig(  # type: ignore[attr-defined]
                    tools=[types.Tool(enterprise_web_search=types.EnterpriseWebSearch())],
                    temperature=0.25,
                    candidate_count=1,
                    max_output_tokens=3000,
                )
                resp = await asyncio.wait_for(
                    asyncio.to_thread(gm.generate_content, prompt, config=cfg),
                    timeout=settings.AGENT_TIMEOUT_QUESTIONING,
                )
                response_text = getattr(resp, "text", None) or str(resp)
        except Exception as _adk_err:
            logger.warning(f"ISA_Questioner: enterprise web search via google.genai unavailable. Error: {_adk_err}")

        # 2) Vertex google_search fallback
        if not response_text:
            try:
                if hasattr(grounding, "GoogleSearch"):
                    vtx_resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            model.generate_content,
                            prompt,
                            google_search=grounding.GoogleSearch(),
                            generation_config=config,
                        ),
                        timeout=settings.AGENT_TIMEOUT_QUESTIONING,
                    )
                    response_text = getattr(vtx_resp, "text", None) or str(vtx_resp)
            except Exception as _gs_err:
                logger.warning(f"ISA_Questioner: google_search param failed, using plain model. Error: {_gs_err}")

        # 3) Plain generation fallback
        if not response_text:
            plain_resp = await asyncio.wait_for(
                asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=config,
                ),
                timeout=settings.AGENT_TIMEOUT_QUESTIONING,
            )
            response_text = getattr(plain_resp, "text", None) or str(plain_resp)

        return response_text
    
    def _parse_questions_response(self, response: str, job_title: str) -> QuestionGenerationOutput:
        """Parse the AI response into structured QuestionGenerationOutput"""
        try:
            candidate, ok = extract_first_balanced_json(response or "")
            if not ok:
                raise ValueError("No JSON found in response")
            questions_data = try_parse_json(candidate)
            
            # Ensure exactly 10 questions
            questions = questions_data.get("questions", [])
            if len(questions) != 10:
                logger.warning(f"Expected 10 questions, got {len(questions)}")
                # Adjust to exactly 10
                if len(questions) > 10:
                    questions = questions[:10]
                else:
                    # Add generic questions to reach 10
                    while len(questions) < 10:
                        questions.append(f"Tell me about your experience relevant to this {job_title} role.")
            
            # Ensure all arrays match the questions length
            question_rationale = questions_data.get("question_rationale", [])
            difficulty_levels = questions_data.get("difficulty_levels", [])
            question_types = questions_data.get("question_types", [])
            
            # Pad arrays to match questions length
            while len(question_rationale) < 10:
                question_rationale.append("Standard assessment question")
            while len(difficulty_levels) < 10:
                difficulty_levels.append("Medium")
            while len(question_types) < 10:
                question_types.append("General")
            
            # Create QuestionGenerationOutput
            return QuestionGenerationOutput(
                questions=questions[:10],
                question_rationale=question_rationale[:10],
                difficulty_levels=difficulty_levels[:10],
                skill_coverage=questions_data.get("skill_coverage", {}),
                question_types=question_types[:10]
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to parse questions response: {e}")
            snippet = (response or "")[:200]
            logger.error(f"❌ Raw response (first 200 chars): {snippet}")
            # Return fallback questions
            return self._create_fallback_questions(job_title, "", "")
    
    def _create_fallback_questions(
        self,
        job_title: str,
        job_description: str,
        candidate_resume: str
    ) -> QuestionGenerationOutput:
        """Create fallback questions when primary generation fails"""
        
        # Generic but professional questions
        questions = [
            f"Tell me about yourself and what interests you about this {job_title} position.",
            "What do you consider your greatest professional strength?",
            "Describe a challenging project you've worked on and how you overcame obstacles.",
            "How do you stay current with industry trends and developments?",
            "Tell me about a time when you had to work with a difficult team member.",
            "What motivates you in your professional work?",
            "Describe a situation where you had to learn something new quickly.",
            "How do you prioritize your work when facing multiple deadlines?",
            "What do you hope to achieve in your career over the next few years?",
            "Do you have any questions about the role or our company?"
        ]
        
        rationale = [
            "Opening question to understand candidate background and motivation",
            "Assess self-awareness and key strengths",
            "Evaluate problem-solving and resilience",
            "Check commitment to professional development",
            "Assess interpersonal and conflict resolution skills",
            "Understand intrinsic motivation and drive",
            "Evaluate learning agility and adaptability",
            "Assess time management and organizational skills",
            "Understand career goals and ambition",
            "Give candidate opportunity to ask questions"
        ]
        
        difficulty = ["Easy", "Easy", "Medium", "Medium", "Medium", "Easy", "Medium", "Medium", "Easy", "Easy"]
        
        types = [
            "Background",
            "Self-Assessment", 
            "Behavioral",
            "Professional Development",
            "Teamwork",
            "Motivation",
            "Learning Agility",
            "Time Management",
            "Career Goals",
            "Candidate Questions"
        ]
        
        return QuestionGenerationOutput(
            questions=questions,
            question_rationale=rationale,
            difficulty_levels=difficulty,
            skill_coverage={
                "Communication": [0, 4, 9],
                "Problem-solving": [2, 6, 7],
                "Professional Development": [3, 8],
                "Teamwork": [4, 5],
                "Adaptability": [6, 7]
            },
            question_types=types
        )
    
    async def validate_questions_quality(
        self,
        questions_output: QuestionGenerationOutput,
        skills_output: Optional[SkillsDetectionOutput] = None
    ) -> Dict[str, Any]:
        """Validate the quality and completeness of generated questions"""
        
        validation_results = {
            "is_valid": True,
            "completeness_score": 0.0,
            "quality_issues": [],
            "recommendations": [],
            "skill_coverage_analysis": {}
        }
        
        # Check question count
        if len(questions_output.questions) != 10:
            validation_results["quality_issues"].append(f"Expected 10 questions, got {len(questions_output.questions)}")
            validation_results["is_valid"] = False
        
        # Check for question variety
        question_types = questions_output.question_types
        unique_types = set(question_types)
        if len(unique_types) < 5:
            validation_results["quality_issues"].append("Limited question type variety")
            validation_results["recommendations"].append("Include more diverse question types")
        
        # Check difficulty distribution
        difficulty_levels = questions_output.difficulty_levels
        difficulty_counts = {"Easy": 0, "Medium": 0, "Hard": 0}
        for level in difficulty_levels:
            level_clean = level.split()[0] if level else "Medium"  # Handle "Medium-Hard" etc.
            if level_clean in difficulty_counts:
                difficulty_counts[level_clean] += 1
        
        # Should have a good mix of difficulties
        if difficulty_counts["Easy"] == 0:
            validation_results["quality_issues"].append("No easy warm-up questions")
        if difficulty_counts["Hard"] == 0:
            validation_results["quality_issues"].append("No challenging questions")
        
        # Check skill coverage if skills provided
        if skills_output:
            key_skills = skills_output.key_skills
            skill_coverage = questions_output.skill_coverage
            
            uncovered_skills = []
            for skill in key_skills:
                # Check if skill is covered (exact match or partial match)
                covered = any(
                    skill.lower() in covered_skill.lower() or covered_skill.lower() in skill.lower()
                    for covered_skill in skill_coverage.keys()
                )
                if not covered:
                    uncovered_skills.append(skill)
            
            if uncovered_skills:
                validation_results["quality_issues"].append(f"Skills not covered: {uncovered_skills}")
                validation_results["recommendations"].append("Ensure all key skills are assessed")
            
            validation_results["skill_coverage_analysis"] = {
                "total_key_skills": len(key_skills),
                "covered_skills": len(key_skills) - len(uncovered_skills),
                "coverage_percentage": ((len(key_skills) - len(uncovered_skills)) / len(key_skills)) * 100,
                "uncovered_skills": uncovered_skills
            }
        
        # Check for question quality
        generic_indicators = ["tell me about", "describe a time", "how do you", "what is your"]
        generic_count = sum(
            1 for question in questions_output.questions
            if any(indicator in question.lower() for indicator in generic_indicators)
        )
        
        if generic_count > 6:
            validation_results["quality_issues"].append("Too many generic question patterns")
            validation_results["recommendations"].append("Make questions more specific and tailored")
        
        # Calculate completeness score
        completeness_factors = [
            ("question_count", len(questions_output.questions) == 10),
            ("rationale_provided", len(questions_output.question_rationale) == 10),
            ("difficulty_assigned", len(questions_output.difficulty_levels) == 10),
            ("types_assigned", len(questions_output.question_types) == 10),
            ("skill_coverage_mapped", len(questions_output.skill_coverage) > 0),
            ("variety_adequate", len(unique_types) >= 5),
            ("difficulty_balanced", difficulty_counts["Easy"] > 0 and difficulty_counts["Hard"] > 0)
        ]
        
        completed_factors = sum(1 for _, completed in completeness_factors if completed)
        validation_results["completeness_score"] = completed_factors / len(completeness_factors)
        
        # Mark as invalid if critical issues found
        if validation_results["completeness_score"] < 0.7:
            validation_results["is_valid"] = False
        
        return validation_results
    
    async def customize_questions_for_voice(
        self,
        questions_output: QuestionGenerationOutput
    ) -> QuestionGenerationOutput:
        """Customize questions for voice interview format"""
        
        # Voice interviews need more conversational, shorter questions
        voice_questions = []
        
        for question in questions_output.questions:
            # Make questions more conversational
            voice_question = question
            
            # Remove complex formatting
            voice_question = voice_question.replace("Tell me about a time when", "Can you share an example of when")
            voice_question = voice_question.replace("Describe a situation where", "Tell me about when")
            
            # Keep questions concise for voice
            if len(voice_question) > 100:
                # Try to shorten while maintaining meaning
                voice_question = voice_question[:97] + "..."
            
            voice_questions.append(voice_question)
        
        # Create voice-optimized output
        return QuestionGenerationOutput(
            questions=voice_questions,
            question_rationale=questions_output.question_rationale,
            difficulty_levels=questions_output.difficulty_levels,
            skill_coverage=questions_output.skill_coverage,
            question_types=questions_output.question_types
        )
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the ISA_Questioner agent"""
        return {
            "agent_name": "ISA_Questioner",
            "description": "Dynamic interview question generation agent",
            "model": self.model_name,
            "capabilities": [
                "Tailored question generation (exactly 10 questions)",
                "Multi-source context integration",
                "Question variety and difficulty balancing",
                "Skill coverage optimization",
                "Voice interview adaptation",
                "Question quality validation"
            ],
            "input_sources": [
                "Job description and requirements",
                "Candidate resume and background",
                "Company research insights",
                "Skills analysis results"
            ],
            "question_types": [
                "Behavioral questions",
                "Situational scenarios",
                "Technical assessments",
                "Cultural fit questions",
                "Experience validation",
                "Problem-solving challenges"
            ],
            "output_format": "QuestionGenerationOutput",
            "question_count": 10,
            "status": "active" if self.model else "inactive"
        }
