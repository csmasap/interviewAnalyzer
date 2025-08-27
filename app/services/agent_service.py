from __future__ import annotations

import json
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import get_settings, Settings
from app.models.schemas import OpportunityDiscussed


class OpenAIAgentService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Please set it in the environment.")
        # Configure timeout and retries on the client
        self._client = AsyncOpenAI(
            api_key=self._settings.openai_api_key,
            base_url=self._settings.openai_base_url or None,
            timeout=float(self._settings.openai_timeout_seconds),
            max_retries=int(self._settings.openai_max_retries),
        )
        self._model = self._settings.openai_model

    @staticmethod
    def _build_prompt(record: OpportunityDiscussed, job_description: Optional[str] = None) -> str:
        payload = record.model_dump()
        context = json.dumps(payload, ensure_ascii=False, indent=2)
        jd_section = f"Job Description Provided:\n{job_description}\n\n" if job_description else ""
        return (
            "You are a brutally honest senior technical recruiter with 15+ years of experience. "
            "You are known for providing realistic, no-sugar-coating assessments that help candidates understand their true market position. "
            "Analyze this candidate data and provide an honest evaluation including:\n\n"
            "1. REALISTIC Skill Assessment: Be specific about actual competency levels vs. market standards\n"
            "2. Experience Gap Analysis: Identify missing years, scope, or depth of experience\n"
            "3. Market Reality Check: How this candidate truly compares to others in the field\n"
            "4. Compensation Alignment: Whether salary expectations match actual market value\n"
            "5. Red Flags: Any concerns about performance, consistency, or capability gaps\n"
            "6. Honest Recommendation: Direct advice on what level/type of roles they should realistically target\n\n"
            "Be encouraging where appropriate, but prioritize honesty over politeness. "
            "If someone is aiming too high, say so clearly. If they need significant development, be specific about what and how much.\n\n"
            f"Candidate Data:\n{context}\n\n"
            f"{jd_section}"
            "Provide your honest assessment:"
        )

    async def analyze_opportunity(self, record: OpportunityDiscussed, job_description: Optional[str] = None) -> str:
        prompt = self._build_prompt(record, job_description)
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are a precise, structured recruiting analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        message = resp.choices[0].message
        return message.content or ""
