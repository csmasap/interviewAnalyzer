from __future__ import annotations

from typing import Optional, List, Dict, Any

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


class OpportunityAnalysisRequest(BaseModel):
    job_description: Optional[str] = None


class OpportunityAnalysisResponse(BaseModel):
    id: str
    analysis: str
    fit_and_gaps: Optional[str] = None


class CareerWorkflowResponse(BaseModel):
    id: str
    analysis: str
    fit_and_gaps: str
    career_path: str
    career_guidance: str
    recommended_jobs: List[Dict[str, Any]]


# New sequential workflow schemas
class WorkflowStartResponse(BaseModel):
    workflow_id: str
    record_id: str
    analysis: str
    fit_and_gaps: str
    next_step: str
    message: str


class CareerPathRequest(BaseModel):
    career_path: str


class CareerFitnessScore(BaseModel):
    score: int  # 0-100
    reasoning: str


class WorkflowStepResponse(BaseModel):
    workflow_id: str
    current_step: str
    completed: bool
    data: Dict[str, Any]
    next_step: Optional[str] = None
    message: Optional[str] = None
    fitness_score: Optional[CareerFitnessScore] = None


class WorkflowFinalResponse(BaseModel):
    workflow_id: str
    record_id: str
    analysis: str
    fit_and_gaps: str
    career_path: str
    career_guidance: str
    recommended_jobs: List[Dict[str, Any]]
    completed: bool


# Job Analyzer schemas
class JobAnalysisRequest(BaseModel):
    job_description: str


class JobAnalysisResponse(BaseModel):
    questions: List[str]


# Interview schemas
class InterviewStartRequest(BaseModel):
    pass  # No additional data needed for starting interview

class InterviewStartResponse(BaseModel):
    interview_id: str
    record_id: str
    position_title: str
    yes_no_questions: List[str]
    message: str

class InterviewYesNoAnswers(BaseModel):
    answers: List[bool]  # True for Yes, False for No

class InterviewOpenEndedResponse(BaseModel):
    interview_id: str
    yes_no_answers: InterviewYesNoAnswers
    open_ended_questions: List[str]
    message: str

class InterviewCompleteRequest(BaseModel):
    interview_id: str
    open_ended_answers: List[str]

class InterviewCompleteResponse(BaseModel):
    interview_id: str
    record_id: str
    summary: str
    message: str