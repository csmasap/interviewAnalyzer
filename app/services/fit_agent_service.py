from __future__ import annotations

import json
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import get_settings, Settings
from app.models.schemas import OpportunityDiscussed


class OpenAIFitAgentService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Please set it in the environment.")
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
        jd_section = (
            "Evaluate the candidate strictly against the following job description. "
            f"Job Description (verbatim):\n{job_description}\n\n"
            if job_description
            else "No job description provided; assess general market fit based on available fields.\n\n"
        )
        return (
            "You are a senior technical recruiter known for honest, realistic assessments. "
            "Your job is to provide a reality check on candidate fit. Be direct about gaps and mismatches.\n\n"
            "Provide a realistic assessment covering:\n"
            "1. CLEAR ALIGNMENTS: What genuinely matches the requirements\n"
            "2. CRITICAL GAPS: Missing skills, experience, or qualifications that are deal-breakers\n"
            "3. EXPERIENCE LEVEL MISMATCH: If they're under/over-qualified, say so bluntly\n"
            "4. RISK FACTORS: Red flags or concerning patterns\n"
            "5. REALISTIC VERDICT: Choose ONE - Strong Fit / Moderate Fit / Weak Fit / Poor Fit\n\n"
            "Don't inflate scores to be kind. Be honest about what employers actually need vs. what this candidate offers. "
            "If someone with minimal experience is targeting senior roles, call it out directly.\n\n"
            f"Candidate Data:\n{context}\n\n"
            f"{jd_section}"
            "Provide your honest fit assessment:"
        )

    async def assess_fit(self, record: OpportunityDiscussed, job_description: Optional[str] = None) -> str:
        prompt = self._build_prompt(record, job_description)
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You produce precise, actionable job fit and gap analyses."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        message = resp.choices[0].message
        return message.content or ""
