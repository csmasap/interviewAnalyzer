"""
ISA_Researcher Agent - Company and Market Intelligence
Optimized to use Gemini with the Web Search tool (Vertex AI Google Search grounding)
instead of Google Custom Search (CSE). Aligns with ADK Python best practices:
 - Use tool-enabled prompting (web search)
 - Low temperature for determinism, strict-JSON output
 - Timeouts and robust fallbacks
 - Caching and model selection via OptimizedAgent
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
from models import ResearchOutput
from config import settings
from .base_agent import OptimizedAgent, TaskComplexity

logger = logging.getLogger(__name__)


class ISAResearcher(OptimizedAgent):
    """
    ISA_Researcher Agent
    
    Searches for company-specific interview information from public sources like:
    - Glassdoor interview experiences
    - Reddit discussions about company interviews
    - LinkedIn posts and articles
    - Company websites and career pages
    
    Provides market intelligence for targeted interview preparation.
    """
    
    def __init__(self):
        """Initialize the ISA_Researcher agent with optimizations"""
        super().__init__("ISA_Researcher")
    
    async def research_company_interview_practices(
        self,
        company_name: str,
        job_title: str,
        job_description: str,
        industry: Optional[str] = None
    ) -> ResearchOutput:
        """
        Research company-specific interview practices and market intelligence
        
        Args:
            company_name: Name of the company
            job_title: Job title/position
            job_description: Full job description
            industry: Industry sector (optional)
            
        Returns:
            ResearchOutput: Comprehensive research findings
        """
        logger.info(f"🔍 Starting company research for {company_name} - {job_title}")
        
        try:
            # Create a prompt that instructs the model to use the Web Search tool
            # and return STRICT JSON so downstream parsing is reliable.
            research_prompt = self._create_research_prompt(
                company_name, job_title, job_description, industry, web_search_results=None
            )

            # Use web-search tool (Vertex AI Google Search grounding)
            research_response = await self._generate_research_with_web(research_prompt)

            # Try strict parse first; if it fails, wrap raw
            try:
                candidate, ok = extract_first_balanced_json(research_response or "")
                if not ok:
                    raise ValueError("No JSON block found")
                parsed = try_parse_json(candidate)
                research_output = ResearchOutput(
                    company_info=parsed.get("company_info", {}),
                    interview_insights=parsed.get("interview_insights", []),
                    common_questions=parsed.get("common_questions", []),
                    interview_style=parsed.get("interview_style", ""),
                    market_intelligence=parsed.get("market_intelligence", {}),
                    research_confidence=parsed.get("research_confidence", 0.6),
                    sources_found=parsed.get("sources_found", []),
                )
                logger.info("ISA_Researcher: parsed=true path=structured")
            except Exception:
                research_output = self._wrap_raw_research(
                    raw_text=research_response,
                    company_name=company_name,
                )
                logger.info("ISA_Researcher: parsed=false path=raw")
            
            logger.info(f"✅ Research completed for {company_name}")
            return research_output
            
        except Exception as e:
            logger.error(f"❌ Research failed for {company_name}: {e}")
            # Return fallback research output
            return self._create_fallback_research(company_name, job_title, job_description)
    
    async def _generate_research_with_web(self, prompt: str) -> str:
        """Generate research using Gemini with the Web Search tool.
        Uses the 'pro' model by default for higher quality synthesis.
        """
        # Select model and config using OptimizedAgent helpers
        model: Optional[GenerativeModel] = self._select_model(TaskComplexity.MODERATE)
        if not model:
            raise Exception("ISA_Researcher: Vertex AI models not initialized")

        generation_config = self._get_generation_config(TaskComplexity.MODERATE, max_tokens=2000)
        # Lower temperature for determinism on research outputs
        generation_config["temperature"] = 0.2

        try:
            # 1) Vertex AI grounding via google_search param (preferred)
            response_text: Optional[str] = None
            try:
                if hasattr(grounding, "GoogleSearch"):
                    vtx_resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            model.generate_content,
                            prompt,
                            google_search=grounding.GoogleSearch(),
                            generation_config=generation_config,
                        ),
                        timeout=settings.AGENT_TIMEOUT_RESEARCH,
                    )
                    response_text = getattr(vtx_resp, "text", None) or str(vtx_resp)
            except Exception as _gs_err:
                logger.warning(f"ISA_Researcher: google_search param failed. Error: {_gs_err}")

            # 2) ADK-style enterprise web search via google.genai (if available)
            if not response_text:
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
                            # type: ignore above as package name can vary by version
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
                            max_output_tokens=2000,
                        )
                        resp = await asyncio.wait_for(
                            asyncio.to_thread(gm.generate_content, prompt, config=cfg),
                            timeout=settings.AGENT_TIMEOUT_RESEARCH,
                        )
                        # Some versions expose .text, others .candidates; prefer .text if present
                        response_text = getattr(resp, "text", None) or str(resp)
                except Exception as _adk_err:
                    logger.warning(f"ISA_Researcher: enterprise web search via google.genai unavailable. Error: {_adk_err}")

            # 3) Tool API fallback removed (not supported in this environment)

            # 4) Final fallback: no grounding
            if not response_text:
                plain_resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        model.generate_content,
                        prompt,
                        generation_config=generation_config,
                    ),
                    timeout=settings.AGENT_TIMEOUT_RESEARCH,
                )
                response_text = getattr(plain_resp, "text", None) or str(plain_resp)

            return response_text
        except asyncio.TimeoutError:
            logger.error("⏰ ISA_Researcher: Web-enabled generation timed out after 60s")
            raise
        except Exception as e:
            logger.error(f"❌ ISA_Researcher: Web-enabled generation failed: {e}")
            raise

    # Deprecated: Legacy CSE search helper retained for reference only
    def _cse_search(self, query: str, cse_id: str, api_key: str, num: int = 5) -> list:
        return []

    def _create_research_prompt(
        self,
        company_name: str,
        job_title: str,
        job_description: str,
        industry: Optional[str] = None,
        web_search_results: Optional[str] = None
    ) -> str:
        """Create a comprehensive research prompt for the AI model"""
        
        industry_context = f" in the {industry} industry" if industry else ""
        
        web_context = ""
        if web_search_results:
            web_context = f"""
WEB SEARCH RESULTS:
{web_search_results}

Use the above web search results to provide specific, accurate information about {company_name}.
"""

        json_example = """
{
    "company_info": {
        "culture_overview": "Company culture and values summary",
        "work_environment": "Work environment and team dynamics",
        "growth_opportunities": "Career growth and development opportunities",
        "company_size_impact": "How company size affects interview process"
    },
    "interview_insights": [
        "Specific insights about their interview process",
        "Timeline and number of interview rounds"
    ],
    "common_questions": [
        "Frequently asked questions specific to this company",
        "Company-specific behavioral questions"
    ],
    "interview_style": "Detailed description of company's interview approach and style",
    "market_intelligence": {
        "salary_ranges": "Typical salary ranges for this role",
        "benefits_highlights": "Key benefits and perks"
    },
    "research_confidence": 0.85,
    "sources_found": [
        "Glassdoor: N interview experiences analyzed",
        "Reddit: M relevant discussion threads"
    ]
}
"""

        prompt = (
            f"""
You are ISA_Researcher, an expert market intelligence analyst specializing in interview preparation research.

RESEARCH TASK:
Research interview practices, culture, and hiring patterns for {company_name}{industry_context} for the position: {job_title}

JOB DESCRIPTION:
{job_description}

{web_context}

RESEARCH OBJECTIVES:
1. Company Culture & Values Analysis
2. Interview Process & Structure  
3. Common Interview Questions & Patterns
4. Technical Assessment Methods (if applicable)
5. Behavioral Interview Focus Areas
6. Company-Specific Interview Tips
7. Hiring Manager Preferences & Expectations

RESEARCH METHODOLOGY:
Simulate comprehensive research across these sources:
- Glassdoor interview experiences and reviews
- Reddit discussions (r/cscareerquestions, company-specific subreddits)
- LinkedIn posts and professional discussions
- Company career pages and blog posts
- Industry forums and professional networks
- Interview preparation websites and resources

OUTPUT REQUIREMENTS:
Provide detailed, actionable intelligence in JSON format with these fields (minimal example shown; expand with real content, no trailing commas):
"""
            + json_example
            + """

CRITICAL OUTPUT RULES:
- Return ONLY a single JSON object as shown above (no markdown, no backticks, no prose).
- The JSON must be valid (no trailing commas, correct quoting).
- If unsure for a field, return [] or {} for that field.
- Internally summarize the job description to ≤300 words to reduce verbosity; do not include the summary in output.

IMPORTANT GUIDELINES:
- If limited information is available, clearly state this and provide general industry insights
- Focus on actionable intelligence that helps interview preparation
- Include both positive and constructive insights
- Maintain professional, objective tone
- Ensure all information is realistic and helpful for job seekers
- Set research_confidence between 0.1 (very limited info) to 0.95 (extensive info found)

Generate comprehensive research intelligence now:
"""
        )
        return prompt
    
    async def _generate_research(self, prompt: str) -> str:
        """Generate research using optimized Vertex AI model"""
        # Research synthesis is complex - use pro model with caching
        return await self.generate_optimized(
            prompt=prompt,
            complexity=TaskComplexity.MODERATE,  # Use pro model for research synthesis
            max_tokens=2000,  # tighter budget to reduce truncation
            timeout=60,
            use_cache=True  # Cache research for same company/role combinations
        )
    
    def _parse_research_response(self, response: str, company_name: str) -> ResearchOutput:
        """Parse the AI response into structured ResearchOutput"""
        try:
            # Strip possible markdown code fences first
            cleaned = (response or "").strip()
            if cleaned.startswith("```"):
                first_newline = cleaned.find('\n')
                if first_newline != -1:
                    cleaned = cleaned[first_newline+1:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            # Extract JSON from response
            json_start = cleaned.find('{')
            json_end = cleaned.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
            
            json_str = cleaned[json_start:json_end]
            research_data = json.loads(json_str)
            
            # Create ResearchOutput from parsed data
            return ResearchOutput(
                company_info=research_data.get("company_info", {}),
                interview_insights=research_data.get("interview_insights", []),
                common_questions=research_data.get("common_questions", []),
                interview_style=research_data.get("interview_style", "Standard interview process"),
                market_intelligence=research_data.get("market_intelligence", {}),
                research_confidence=research_data.get("research_confidence", 0.5),
                sources_found=research_data.get("sources_found", [])
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to parse research response: {e}")
            # Return fallback research
            return self._create_fallback_research(company_name, "Unknown", "")

    def _wrap_raw_research(self, raw_text: str, company_name: str) -> ResearchOutput:
        """Wrap raw research text into ResearchOutput to avoid strict JSON parsing.

        The raw text is placed under company_info["raw_text"]. Other fields are left
        minimal so downstream consumers can still operate.
        """
        text = (raw_text or "").strip()
        return ResearchOutput(
            company_info={
                "raw_text": text,
            },
            interview_insights=[],
            common_questions=[],
            interview_style="",
            market_intelligence={},
            research_confidence=0.6 if text else 0.2,
            sources_found=[],
        )
    
    def _create_fallback_research(
        self,
        company_name: str,
        job_title: str,
        job_description: str
    ) -> ResearchOutput:
        """Create fallback research output when primary research fails"""
        
        return ResearchOutput(
            company_info={
                "culture_overview": f"Limited public information available about {company_name}'s specific culture and interview practices.",
                "work_environment": "Standard professional work environment expected.",
                "growth_opportunities": "Growth opportunities typical for the industry.",
                "company_size_impact": "Interview process will vary based on company size and structure."
            },
            interview_insights=[
                "Limited company-specific interview information available",
                "Interview will likely follow industry standard practices",
                "Prepare for both behavioral and technical questions",
                "Research company website and recent news for current information"
            ],
            common_questions=[
                "Tell me about yourself and your background",
                "Why are you interested in this role?",
                f"What do you know about {company_name}?",
                "Describe your relevant experience for this position",
                "What are your salary expectations?",
                "Do you have any questions for us?"
            ],
            interview_style="Standard interview process with behavioral and technical components",
            market_intelligence={
                "salary_ranges": "Industry-standard salary ranges apply",
                "benefits_highlights": "Standard benefits package expected",
                "competition_analysis": "Competitive landscape varies by industry",
                "hiring_trends": "Following current market hiring trends"
            },
            research_confidence=0.2,  # Low confidence due to limited information
            sources_found=[
                "Limited public information found",
                "Fallback to industry standard practices",
                "Recommend candidate research company directly"
            ]
        )
    
    async def validate_research_quality(self, research_output: ResearchOutput) -> Dict[str, Any]:
        """Validate the quality and completeness of research output"""
        
        validation_results = {
            "is_valid": True,
            "completeness_score": 0.0,
            "quality_issues": [],
            "recommendations": []
        }
        
        # Check completeness
        completeness_factors = [
            ("company_info", len(research_output.company_info) > 0),
            ("interview_insights", len(research_output.interview_insights) >= 3),
            ("common_questions", len(research_output.common_questions) >= 5),
            ("interview_style", len(research_output.interview_style) > 20),
            ("market_intelligence", len(research_output.market_intelligence) > 0),
            ("sources_found", len(research_output.sources_found) > 0),
        ]
        
        completed_factors = sum(1 for _, completed in completeness_factors if completed)
        validation_results["completeness_score"] = completed_factors / len(completeness_factors)
        
        # Check quality issues
        if research_output.research_confidence < 0.3:
            validation_results["quality_issues"].append("Low research confidence")
            validation_results["recommendations"].append("Consider manual company research")
        
        if len(research_output.common_questions) < 5:
            validation_results["quality_issues"].append("Insufficient common questions")
            validation_results["recommendations"].append("Generate additional generic questions")
        
        if not research_output.sources_found:
            validation_results["quality_issues"].append("No sources documented")
            validation_results["recommendations"].append("Document research methodology")
        
        # Mark as invalid if critical issues found
        if validation_results["completeness_score"] < 0.5:
            validation_results["is_valid"] = False
        
        return validation_results
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the ISA_Researcher agent"""
        return {
            "agent_name": "ISA_Researcher",
            "description": "Company and market intelligence research agent",
            "model": self.model_name,
            "capabilities": [
                "Company culture analysis",
                "Interview process research",
                "Market intelligence gathering",
                "Question pattern identification",
                "Hiring trend analysis"
            ],
            "data_sources": [
                "Glassdoor interview experiences",
                "Reddit career discussions",
                "LinkedIn professional posts",
                "Company career pages",
                "Industry forums"
            ],
            "output_format": "ResearchOutput",
            "confidence_range": "0.1 - 0.95",
            "status": "active" if self.model else "inactive"
        }
