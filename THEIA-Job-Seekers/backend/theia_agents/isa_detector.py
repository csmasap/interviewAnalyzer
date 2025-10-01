"""
ISA_Detector Agent - Skills and Competency Analysis
Google Vertex AI agent for analyzing job descriptions and detecting key skills/competencies.
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
from models import SkillsDetectionOutput
from config import settings
from .base_agent import OptimizedAgent, TaskComplexity

logger = logging.getLogger(__name__)


class ISADetector(OptimizedAgent):
    """
    ISA_Detector Agent
    
    Analyzes job descriptions to identify and extract:
    - 5-7 key skills and competencies required for success
    - Technical requirements and qualifications
    - Soft skills and cultural fit requirements
    - Experience level expectations
    - Evaluation criteria for candidate assessment
    
    Creates a comprehensive scorecard for interview evaluation.
    """
    
    def __init__(self):
        """Initialize the ISA_Detector agent with optimizations"""
        super().__init__("ISA_Detector")
    
    async def analyze_job_requirements(
        self,
        job_description: str,
        job_title: str,
        company_name: str,
        industry: Optional[str] = None,
        company_research: Optional[Dict[str, Any]] = None
    ) -> SkillsDetectionOutput:
        """
        Analyze job description to detect key skills and competencies
        
        Args:
            job_description: Complete job description text
            job_title: Job title/position
            company_name: Company name
            industry: Industry sector (optional)
            company_research: Research data from ISA_Researcher (optional)
            
        Returns:
            SkillsDetectionOutput: Structured skills and competencies analysis
        """
        logger.info(f"🔍 Analyzing job requirements for {job_title} at {company_name}")
        
        try:
            # Create skills analysis prompt
            analysis_prompt = self._create_skills_analysis_prompt(
                job_description, job_title, company_name, industry, company_research
            )
            
            # Prefer grounded analysis using web search for role/industry signal
            try:
                analysis_response = await self._generate_analysis_with_web(analysis_prompt)
            except Exception:
                analysis_response = await self._generate_analysis(analysis_prompt)
            
            # Parse and structure the analysis output
            skills_output = self._parse_skills_response(analysis_response, job_title)
            
            logger.info(f"✅ Skills analysis completed for {job_title}")
            return skills_output
            
        except Exception as e:
            logger.error(f"❌ Skills analysis failed for {job_title}: {e}")
            logger.error(f"❌ CRITICAL: ISA_Detector MUST analyze job description - retrying with basic prompt")
            
            # Instead of fallback, retry with a simpler approach
            try:
                simple_prompt = f"""
Analyze this job description and extract 5-7 key skills required:

JOB: {job_title} at {company_name}
DESCRIPTION: {job_description}

Return only a JSON object with:
- key_skills: list of 5-7 specific skills from the job description
- experience_level: required experience level
- job_analysis_summary: 2-sentence summary

JSON:"""
                
                response = await self._generate_analysis(simple_prompt)
                return self._parse_skills_response(response, job_title)
                
            except Exception as retry_error:
                logger.error(f"❌ ISA_Detector retry failed: {retry_error}")
                # Only now use minimal fallback, but still try to extract from job description
                return self._extract_skills_from_job_description(job_description, job_title)
    
    def _create_skills_analysis_prompt(
        self,
        job_description: str,
        job_title: str,
        company_name: str,
        industry: Optional[str] = None,
        company_research: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a comprehensive skills analysis prompt for the AI model"""
        
        industry_context = f" in the {industry} industry" if industry else ""
        
        company_context = ""
        if company_research:
            company_context = f"""
COMPANY RESEARCH CONTEXT:
Company Culture: {company_research.get('company_info', {}).get('culture_overview', 'N/A')}
Interview Style: {company_research.get('interview_style', 'Standard')}
Key Values: {company_research.get('market_intelligence', {}).get('company_values', 'N/A')}
"""
        
        prompt = f"""
You are ISA_Detector, an expert job analysis specialist and competency assessment expert.

ANALYSIS TASK:
Analyze the following job description to identify the 5-7 most critical skills and competencies needed for success in this role.

JOB DETAILS:
Position: {job_title}
Company: {company_name}{industry_context}

{company_context}

JOB DESCRIPTION:
{job_description}

ANALYSIS OBJECTIVES:
1. Identify 5-7 KEY SKILLS that are absolutely critical for success
2. Categorize skills into technical and soft skills
3. Determine experience level requirements
4. Create evaluation criteria for each skill
5. Analyze cultural fit requirements
6. Generate a comprehensive scorecard framework

ANALYSIS METHODOLOGY:
- Analyze explicit requirements (must-have skills)
- Identify implicit requirements (reading between the lines)
- Consider industry standards and best practices
- Factor in company culture and values
- Prioritize skills by importance and impact

OUTPUT REQUIREMENTS:
Provide detailed analysis in JSON format with these exact fields:

{{
    "key_skills": [
        "Skill 1: Most critical skill",
        "Skill 2: Second most important",
        "Skill 3: Third critical skill",
        "Skill 4: Fourth important skill",
        "Skill 5: Fifth key skill",
        "Skill 6: Sixth skill (if applicable)",
        "Skill 7: Seventh skill (if applicable)"
    ],
    "competencies": [
        "Core competency 1",
        "Core competency 2",
        "Core competency 3",
        "Leadership competency (if applicable)",
        "Strategic thinking (if applicable)"
    ],
    "technical_requirements": [
        "Specific technical skill 1",
        "Technical tool/platform 2",
        "Programming language/framework 3",
        "Certification or qualification 4"
    ],
    "soft_skills": [
        "Communication skills",
        "Problem-solving ability",
        "Teamwork and collaboration",
        "Adaptability and learning agility",
        "Cultural fit requirement"
    ],
    "experience_level": "Entry-level/Mid-level/Senior-level/Executive with specific years",
    "scorecard_criteria": {{
        "Skill 1": "How to evaluate this skill (behavioral indicators, questions to ask)",
        "Skill 2": "Evaluation criteria for skill 2",
        "Skill 3": "Assessment approach for skill 3",
        "Skill 4": "Measurement criteria for skill 4",
        "Skill 5": "Evaluation framework for skill 5"
    }},
    "job_analysis_summary": "Comprehensive 2-3 sentence summary of the role requirements and ideal candidate profile"
}}

CRITICAL GUIDELINES:
- Limit key_skills to exactly 5-7 items (most important ones)
- Make skills specific and measurable
- Include both technical and soft skills in key_skills
- Ensure scorecard_criteria provides actionable evaluation methods
- Consider the full candidate journey and growth potential
- Factor in remote work capabilities if mentioned
- Include industry-specific requirements
- Balance must-have vs nice-to-have skills

CRITICAL OUTPUT RULES:
- Return ONLY a single JSON object as shown above (no markdown, no backticks, no prose).
- The JSON must be valid (no trailing commas, correct quoting).
- Do not include any explanation before or after the JSON.

Generate comprehensive skills analysis now:
"""
        return prompt
    
    async def _generate_analysis(self, prompt: str) -> str:
        """Generate skills analysis using optimized Vertex AI model"""
        # Skills detection is moderately complex - use flash model for speed
        return await self.generate_optimized(
            prompt=prompt,
            complexity=TaskComplexity.SIMPLE,  # flash
            max_tokens=1800,  # tighter to avoid truncation and drift
            timeout=30,  # Reduced from 120s to 30s for flash model
            use_cache=True  # Cache skills detection for similar job descriptions
        )

    async def _generate_analysis_with_web(self, prompt: str) -> str:
        """Generate skills analysis using Gemini with Web Search tool for grounding.
        Primary: Enterprise Web Search via google.generativeai; fallback: Vertex google_search; final: plain.
        """
        model: Optional[GenerativeModel] = self._select_model(TaskComplexity.MODERATE)
        if not model:
            raise Exception("ISA_Detector: Vertex AI models not initialized")
        config = self._get_generation_config(TaskComplexity.MODERATE, max_tokens=2500)
        config["temperature"] = 0.2

        # 1) Try Enterprise Web Search via google.generativeai
        response_text: Optional[str] = None
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
                    temperature=0.2,
                    candidate_count=1,
                    max_output_tokens=2500,
                )
                resp = await asyncio.wait_for(
                    asyncio.to_thread(gm.generate_content, prompt, config=cfg),
                    timeout=settings.AGENT_TIMEOUT_DETECTION,
                )
                response_text = getattr(resp, "text", None) or str(resp)
        except Exception as _adk_err:
            logger.warning(f"ISA_Detector: enterprise web search via google.genai unavailable. Error: {_adk_err}")

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
                        timeout=settings.AGENT_TIMEOUT_DETECTION,
                    )
                    response_text = getattr(vtx_resp, "text", None) or str(vtx_resp)
            except Exception as _gs_err:
                logger.warning(f"ISA_Detector: google_search param failed, using plain model. Error: {_gs_err}")

        # 3) Plain generation fallback
        if not response_text:
            plain_resp = await asyncio.wait_for(
                asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=config,
                ),
                timeout=settings.AGENT_TIMEOUT_DETECTION,
            )
            response_text = getattr(plain_resp, "text", None) or str(plain_resp)

        return response_text
    
    def _parse_skills_response(self, response: str, job_title: str) -> SkillsDetectionOutput:
        """Parse the AI response into structured SkillsDetectionOutput"""
        try:
            candidate, ok = extract_first_balanced_json(response or "")
            if not ok:
                raise ValueError("No JSON found in response")
            skills_data = try_parse_json(candidate)
            
            # Ensure key_skills has 5-7 items
            key_skills = skills_data.get("key_skills", [])
            if len(key_skills) > 7:
                key_skills = key_skills[:7]
            elif len(key_skills) < 5:
                # Add generic skills if needed
                while len(key_skills) < 5:
                    key_skills.append(f"Professional skill {len(key_skills) + 1}")
            
            # Create SkillsDetectionOutput from parsed data
            return SkillsDetectionOutput(
                key_skills=key_skills,
                competencies=skills_data.get("competencies", []),
                technical_requirements=skills_data.get("technical_requirements", []),
                soft_skills=skills_data.get("soft_skills", []),
                experience_level=skills_data.get("experience_level", "Mid-level"),
                scorecard_criteria=skills_data.get("scorecard_criteria", {}),
                job_analysis_summary=skills_data.get("job_analysis_summary", f"Analysis for {job_title} position")
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to parse skills response: {e}")
            logger.error(f"❌ Raw response (first 500 chars): {response[:500] if response else 'No response'}")
            # Return fallback analysis
            return self._create_fallback_analysis(job_title, "")
    
    def _create_fallback_analysis(self, job_title: str, job_description: str) -> SkillsDetectionOutput:
        """Create fallback skills analysis when primary analysis fails"""
        
        # Extract basic skills from job title
        title_lower = job_title.lower()
        
        # Determine basic skills based on common job patterns
        if any(word in title_lower for word in ['developer', 'engineer', 'programmer']):
            key_skills = [
                "Programming and software development",
                "Problem-solving and analytical thinking",
                "Technical troubleshooting",
                "Code review and quality assurance",
                "Collaboration and teamwork"
            ]
            technical_requirements = [
                "Programming languages",
                "Development frameworks",
                "Version control systems",
                "Testing methodologies"
            ]
        elif any(word in title_lower for word in ['manager', 'director', 'lead']):
            key_skills = [
                "Leadership and team management",
                "Strategic planning and execution",
                "Communication and interpersonal skills",
                "Project management",
                "Decision-making and problem-solving"
            ]
            technical_requirements = [
                "Management tools and software",
                "Budgeting and financial planning",
                "Performance management systems"
            ]
        elif any(word in title_lower for word in ['sales', 'business', 'account']):
            key_skills = [
                "Sales and business development",
                "Client relationship management",
                "Communication and presentation skills",
                "Negotiation and closing",
                "Market analysis and strategy"
            ]
            technical_requirements = [
                "CRM software",
                "Sales analytics tools",
                "Presentation software"
            ]
        else:
            # Generic professional skills
            key_skills = [
                "Professional communication",
                "Problem-solving and critical thinking",
                "Time management and organization",
                "Collaboration and teamwork",
                "Adaptability and learning agility"
            ]
            technical_requirements = [
                "Industry-standard software",
                "Professional communication tools",
                "Data analysis capabilities"
            ]
        
        return SkillsDetectionOutput(
            key_skills=key_skills,
            competencies=[
                "Professional competency",
                "Technical competency",
                "Communication competency",
                "Problem-solving competency"
            ],
            technical_requirements=technical_requirements,
            soft_skills=[
                "Communication skills",
                "Teamwork and collaboration",
                "Problem-solving ability",
                "Adaptability",
                "Professional demeanor"
            ],
            experience_level="Mid-level (3-5 years experience)",
            scorecard_criteria={
                skill: f"Evaluate candidate's proficiency in {skill.lower()} through behavioral questions and examples"
                for skill in key_skills
            },
            job_analysis_summary=f"Fallback analysis for {job_title} position focusing on core professional competencies."
        )
    
    async def validate_skills_analysis(self, skills_output: SkillsDetectionOutput) -> Dict[str, Any]:
        """Validate the quality and completeness of skills analysis"""
        
        validation_results = {
            "is_valid": True,
            "completeness_score": 0.0,
            "quality_issues": [],
            "recommendations": []
        }
        
        # Check key skills count (should be 5-7)
        skills_count = len(skills_output.key_skills)
        if skills_count < 5:
            validation_results["quality_issues"].append(f"Too few key skills ({skills_count})")
            validation_results["recommendations"].append("Add more critical skills")
        elif skills_count > 7:
            validation_results["quality_issues"].append(f"Too many key skills ({skills_count})")
            validation_results["recommendations"].append("Focus on top 7 most critical skills")
        
        # Check completeness
        completeness_factors = [
            ("key_skills", len(skills_output.key_skills) >= 5),
            ("competencies", len(skills_output.competencies) >= 3),
            ("technical_requirements", len(skills_output.technical_requirements) >= 2),
            ("soft_skills", len(skills_output.soft_skills) >= 3),
            ("experience_level", len(skills_output.experience_level) > 5),
            ("scorecard_criteria", len(skills_output.scorecard_criteria) >= 5),
            ("job_analysis_summary", len(skills_output.job_analysis_summary) > 20),
        ]
        
        completed_factors = sum(1 for _, completed in completeness_factors if completed)
        validation_results["completeness_score"] = completed_factors / len(completeness_factors)
        
        # Check scorecard criteria quality
        if len(skills_output.scorecard_criteria) < len(skills_output.key_skills):
            validation_results["quality_issues"].append("Missing scorecard criteria for some skills")
            validation_results["recommendations"].append("Provide evaluation criteria for all key skills")
        
        # Check for generic vs specific skills
        generic_indicators = ["skill", "ability", "competency", "professional"]
        generic_count = sum(
            1 for skill in skills_output.key_skills 
            if any(indicator in skill.lower() for indicator in generic_indicators)
        )
        
        if generic_count > 2:
            validation_results["quality_issues"].append("Too many generic skill descriptions")
            validation_results["recommendations"].append("Make skills more specific and measurable")
        
        # Mark as invalid if critical issues found
        if validation_results["completeness_score"] < 0.7:
            validation_results["is_valid"] = False
        
        return validation_results
    
    async def create_interview_scorecard(
        self,
        skills_output: SkillsDetectionOutput,
        company_name: str
    ) -> Dict[str, Any]:
        """Create a comprehensive interview scorecard based on detected skills"""
        
        scorecard = {
            "company": company_name,
            "created_at": datetime.utcnow().isoformat(),
            "evaluation_framework": {
                "scoring_scale": "1-10 scale (1=Poor, 5=Average, 10=Excellent)",
                "evaluation_method": "Behavioral and situational questions",
                "assessment_areas": len(skills_output.key_skills)
            },
            "key_skills_assessment": {},
            "competency_evaluation": {},
            "technical_assessment": {},
            "soft_skills_evaluation": {},
            "overall_scoring": {
                "technical_weight": 0.4,
                "soft_skills_weight": 0.3,
                "experience_weight": 0.2,
                "cultural_fit_weight": 0.1
            }
        }
        
        # Create detailed assessment for each key skill
        for i, skill in enumerate(skills_output.key_skills, 1):
            scorecard["key_skills_assessment"][f"skill_{i}"] = {
                "skill_name": skill,
                "evaluation_criteria": skills_output.scorecard_criteria.get(skill, f"Assess {skill}"),
                "sample_questions": [
                    f"Can you describe a situation where you used {skill.lower()}?",
                    f"How do you typically approach {skill.lower()} in your work?",
                    f"What challenges have you faced with {skill.lower()}?"
                ],
                "scoring_rubric": {
                    "1-3": "Limited experience or understanding",
                    "4-6": "Some experience with basic proficiency",
                    "7-8": "Strong experience with good proficiency",
                    "9-10": "Expert level with exceptional proficiency"
                }
            }
        
        # Add competency evaluation
        for comp in skills_output.competencies:
            scorecard["competency_evaluation"][comp.lower().replace(" ", "_")] = {
                "description": comp,
                "assessment_method": "Behavioral interview questions",
                "weight": 1.0 / len(skills_output.competencies)
            }
        
        return scorecard
    
    def _extract_skills_from_job_description(self, job_description: str, job_title: str) -> SkillsDetectionOutput:
        """Extract skills directly from job description text when AI fails"""
        logger.info(f"🔍 Extracting skills from job description for {job_title}")
        
        # Analyze the actual job description content
        jd_lower = job_description.lower()
        
        # Extract skills mentioned in the job description
        skill_keywords = {
            "communication": ["communication", "interpersonal", "presentation", "writing", "verbal"],
            "leadership": ["leadership", "lead", "manage", "supervise", "direct", "mentor"],
            "technical": ["technical", "software", "systems", "tools", "platform", "technology"],
            "analytical": ["analytical", "analysis", "data", "metrics", "reporting", "insights"],
            "project management": ["project", "planning", "coordination", "timeline", "deliverables"],
            "problem solving": ["problem", "solution", "troubleshoot", "resolve", "critical thinking"],
            "collaboration": ["collaboration", "teamwork", "cross-functional", "stakeholder"],
            "strategic": ["strategic", "strategy", "planning", "vision", "objectives"]
        }
        
        found_skills = []
        for skill, keywords in skill_keywords.items():
            if any(keyword in jd_lower for keyword in keywords):
                found_skills.append(skill.title())
        
        # Add any specific skills mentioned in the job description
        specific_skills = []
        if "hr" in jd_lower or "human resources" in jd_lower:
            specific_skills.extend(["HR Business Partnership", "Employment Law Knowledge", "HRIS Systems"])
        if "sales" in jd_lower or "business development" in jd_lower:
            specific_skills.extend(["Sales Strategy", "Client Relationship Management", "Revenue Growth"])
        if "engineering" in jd_lower or "development" in jd_lower:
            specific_skills.extend(["Software Development", "System Architecture", "Code Quality"])
        
        # Combine and limit to 5-7 skills
        all_skills = (specific_skills + found_skills)[:7]
        if len(all_skills) < 5:
            all_skills.extend(["Professional Communication", "Problem-Solving", "Time Management"][:5-len(all_skills)])
        
        # Determine experience level from job description
        experience_level = "Mid-level"
        if any(term in jd_lower for term in ["senior", "lead", "principal", "7+ years", "8+ years"]):
            experience_level = "Senior-level"
        elif any(term in jd_lower for term in ["entry", "junior", "0-2 years", "new grad"]):
            experience_level = "Entry-level"
        
        return SkillsDetectionOutput(
            key_skills=all_skills,
            competencies=[f"{skill} competency" for skill in all_skills[:4]],
            technical_requirements=specific_skills[:3] if specific_skills else ["Industry-standard tools"],
            soft_skills=["Communication", "Teamwork", "Adaptability", "Problem-solving"],
            experience_level=experience_level,
            scorecard_criteria={skill: f"Evaluate {skill.lower()} through behavioral examples" for skill in all_skills},
            job_analysis_summary=f"Analysis of {job_title} position based on job description content and requirements."
        )
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the ISA_Detector agent"""
        return {
            "agent_name": "ISA_Detector",
            "description": "Skills and competency analysis agent",
            "model": self.model_name,
            "capabilities": [
                "Job description analysis",
                "Key skills identification (5-7 skills)",
                "Technical requirements extraction",
                "Soft skills assessment",
                "Experience level determination",
                "Scorecard criteria creation"
            ],
            "analysis_areas": [
                "Technical competencies",
                "Soft skills requirements",
                "Experience level expectations",
                "Cultural fit indicators",
                "Performance evaluation criteria"
            ],
            "output_format": "SkillsDetectionOutput",
            "skill_limit": "5-7 key skills",
            "status": "active" if self.model else "inactive"
        }
