from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Candidate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    resume_text: Optional[str] = None


class OpportunityDiscussed(BaseModel):
    id: str
    name: Optional[str] = None
    candidate: Optional[Candidate] = None

    sum_scorecard_evaluation: Optional[float] = None
    reason_capable_of: Optional[str] = None
    candidate_interviews_summary: Optional[str] = None
    salary_expectations: Optional[str] = None
    scorecard_full_candidate_report: Optional[str] = None
    ai_interview_summary: Optional[str] = None
    interview_candidate_score: Optional[float] = None
    interview_candidate_feedback: Optional[str] = None
