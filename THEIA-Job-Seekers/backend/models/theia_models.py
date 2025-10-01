"""
THEIA Interview Prep System - Data Models
Pydantic models for the THEIA interview preparation system.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


# Enums for interview system
class InterviewMode(str, Enum):
    """Interview mode selection"""
    TEXT = "text"
    VOICE = "voice"


class InterviewPhase(str, Enum):
    """Interview phases"""
    INITIALIZATION = "initialization"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    QUESTION_GENERATION = "question_generation"
    INTERVIEW_ACTIVE = "interview_active"
    EVALUATION = "evaluation"
    COMPLETED = "completed"
    FAILED = "failed"


class InterviewStatus(str, Enum):
    """Interview status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


# Input Models
class InterviewRequest(BaseModel):
    """Request to start an interview"""
    user_id: str = Field(..., description="Salesforce Contact ID")
    job_description: str = Field(..., description="Job description for interview preparation")
    company_name: str = Field(..., description="Company name for targeted preparation")
    interview_mode: InterviewMode = Field(..., description="Text or voice interview mode")
    job_title: Optional[str] = Field(None, description="Specific job title")


class UserMessage(BaseModel):
    """User message during interview"""
    message: str = Field(..., description="User's message or answer")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VoiceMessage(BaseModel):
    """Voice message data"""
    audio_data: bytes = Field(..., description="Audio data from user")
    sample_rate: int = Field(default=16000, description="Audio sample rate")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Agent Output Models
class ResearchOutput(BaseModel):
    """Output from ISA_Researcher agent"""
    company_info: Dict[str, Any] = Field(..., description="Company information and culture")
    interview_insights: List[str] = Field(..., description="Interview insights from market research")
    common_questions: List[str] = Field(..., description="Common questions asked at this company")
    interview_style: str = Field(..., description="Company's interview style and approach")
    market_intelligence: Dict[str, Any] = Field(..., description="Market intelligence data")
    research_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in research findings")
    sources_found: List[str] = Field(..., description="Sources of information found")


class SkillsDetectionOutput(BaseModel):
    """Output from ISA_Detector agent"""
    key_skills: List[str] = Field(..., max_items=7, description="5-7 key skills required for the job")
    competencies: List[str] = Field(..., description="Core competencies needed")
    technical_requirements: List[str] = Field(..., description="Technical skills required")
    soft_skills: List[str] = Field(..., description="Soft skills and cultural fit requirements")
    experience_level: str = Field(..., description="Required experience level")
    scorecard_criteria: Dict[str, str] = Field(..., description="Evaluation criteria for each skill")
    job_analysis_summary: str = Field(..., description="Summary of job requirements analysis")


class QuestionGenerationOutput(BaseModel):
    """Output from ISA_Questioner agent"""
    questions: List[str] = Field(..., max_items=10, description="10 tailored interview questions")
    question_rationale: List[str] = Field(..., description="Rationale for each question")
    difficulty_levels: List[str] = Field(..., description="Difficulty level of each question")
    skill_coverage: Dict[str, List[int]] = Field(..., description="Which questions cover which skills")
    question_types: List[str] = Field(..., description="Type of each question (behavioral, technical, etc.)")


class PreparedInterviewContext(BaseModel):
    """Normalized bundle produced by AgentCoordinator for downstream agents.
    This structure is intentionally consumption-oriented and stable so
    text and voice agents can rely on consistent keys.
    """
    # Identity and session
    session_id: str = Field(..., description="Interview session id")
    company_name: str = Field(...)
    job_title: Optional[str] = Field(None)
    interview_mode: Optional[str] = Field(None, description="Selected mode at start (text/voice)")

    # Inputs
    job_description: str = Field(...)
    candidate_resume: Optional[str] = Field(None)

    # Extracted/derived signals
    key_skills: List[str] = Field(default_factory=list, description="Primary skills from ISA_Detector")
    competencies: List[str] = Field(default_factory=list)
    technical_requirements: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    experience_level: Optional[str] = Field(None)
    scorecard_criteria: Dict[str, str] = Field(default_factory=dict, description="Skill → rubric criteria")

    # Company research summary
    interview_overview: Optional[str] = Field(None)
    interview_style: Optional[str] = Field(None)
    common_questions: List[str] = Field(default_factory=list)
    market_intelligence: Dict[str, Any] = Field(default_factory=dict)
    sources: List[str] = Field(default_factory=list)

    # Questions planned for interview
    questions: List[str] = Field(default_factory=list)
    question_rationale: List[str] = Field(default_factory=list)
    difficulty_levels: List[str] = Field(default_factory=list)
    question_types: List[str] = Field(default_factory=list)
    skill_coverage: Dict[str, List[int]] = Field(default_factory=dict)

    # Timestamps / meta
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class EvaluationOutput(BaseModel):
    """Output from ISA_Evaluator agent"""
    job_matching_score: float = Field(..., ge=0.0, le=10.0, description="Job matching score (0-10)")
    interviewing_skills: Dict[str, float] = Field(..., description="Interviewing skills scores (0-10)")
    skill_assessments: Dict[str, float] = Field(..., description="Individual skill assessments")
    strengths: List[str] = Field(..., description="Candidate's strengths")
    improvement_areas: List[str] = Field(..., description="Areas for improvement")
    overall_feedback: str = Field(..., description="Comprehensive feedback")
    recommendations: List[str] = Field(..., description="Specific recommendations for improvement")
    interview_readiness: float = Field(..., ge=0.0, le=10.0, description="Overall interview readiness score")


# Session and State Models
class InterviewSession(BaseModel):
    """Interview session data"""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="Salesforce Contact ID")
    interview_mode: InterviewMode = Field(..., description="Text or voice mode")
    phase: InterviewPhase = Field(default=InterviewPhase.INITIALIZATION, description="Current interview phase")
    status: InterviewStatus = Field(default=InterviewStatus.PENDING, description="Interview status")
    
    # Job and company information
    job_description: str = Field(..., description="Job description")
    company_name: str = Field(..., description="Company name")
    job_title: Optional[str] = Field(None, description="Job title")
    
    # Agent outputs
    research_output: Optional[ResearchOutput] = Field(None, description="Research agent results")
    skills_output: Optional[SkillsDetectionOutput] = Field(None, description="Skills detection results")
    questions_output: Optional[QuestionGenerationOutput] = Field(None, description="Generated questions")
    evaluation_output: Optional[EvaluationOutput] = Field(None, description="Final evaluation")
    
    # Interview progress
    current_question_index: int = Field(default=0, description="Current question index")
    answers: List[str] = Field(default_factory=list, description="User's answers")
    interview_transcript: List[Dict[str, Any]] = Field(default_factory=list, description="Full interview transcript")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")

    @validator('updated_at', pre=True, always=True)
    def set_updated_at(cls, v):
        return datetime.utcnow()


class InterviewProgress(BaseModel):
    """Interview progress information"""
    phase: InterviewPhase
    status: InterviewStatus
    progress_percentage: float = Field(..., ge=0.0, le=100.0)
    current_step: str
    message: str
    questions_completed: int = Field(default=0)
    total_questions: int = Field(default=10)


# WebSocket Message Models
class WebSocketMessage(BaseModel):
    """Base WebSocket message"""
    type: str = Field(..., description="Message type")
    data: Dict[str, Any] = Field(..., description="Message data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StatusMessage(BaseModel):
    """Status update message"""
    type: str = Field(default="status", description="Message type")
    phase: InterviewPhase
    status: InterviewStatus
    message: str
    progress: float = Field(..., ge=0.0, le=100.0)


class QuestionMessage(BaseModel):
    """Question message to user"""
    type: str = Field(default="question", description="Message type")
    question: str
    question_number: int
    total_questions: int
    is_final: bool = Field(default=False)


class AIResponseMessage(BaseModel):
    """AI response message"""
    type: str = Field(default="ai_response", description="Message type")
    message: str
    is_question: bool = Field(default=False)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatInteractionMessage(BaseModel):
    """ISA_Chat interaction message"""
    type: str = Field(default="chat_interaction")
    message: str
    interaction_type: str  # "question", "feedback", "guidance", "validation"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnswerValidationResult(BaseModel):
    """Answer validation from ISA_Chat"""
    is_valid: bool
    relevance_score: float
    feedback_message: str
    requires_clarification: bool
    follow_up_question: Optional[str] = None


class EvaluationMessage(BaseModel):
    """Evaluation results message"""
    type: str = Field(default="evaluation", description="Message type")
    evaluation: EvaluationOutput
    session_complete: bool = Field(default=True)


# Salesforce Integration Models
class SalesforceContact(BaseModel):
    """Salesforce Contact information"""
    id: str = Field(..., description="Salesforce Contact ID")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    email: Optional[str] = Field(None, description="Email address")
    resume_txt: Optional[str] = Field(None, description="Resume text content")


class TheiaInterviewRecord(BaseModel):
    """THEIA_Interview__c Salesforce record"""
    contact_id: str = Field(..., description="Related Contact ID")
    job_description: str = Field(..., description="Job description")
    company_name: str = Field(..., description="Company name")
    job_title: Optional[str] = Field(None, description="Job title")
    interview_mode: str = Field(..., description="Interview mode (text/voice)")
    
    # Research data
    company_research: Optional[str] = Field(None, description="Company research results")
    market_intelligence: Optional[str] = Field(None, description="Market intelligence data")
    
    # Skills and questions
    detected_skills: Optional[str] = Field(None, description="Detected skills (JSON)")
    generated_questions: Optional[str] = Field(None, description="Generated questions (JSON)")
    
    # Interview data
    interview_transcript: Optional[str] = Field(None, description="Full interview transcript")
    user_answers: Optional[str] = Field(None, description="User answers (JSON)")
    
    # Evaluation results
    job_matching_score: Optional[float] = Field(None, description="Job matching score")
    interviewing_skills_scores: Optional[str] = Field(None, description="Interviewing skills scores (JSON)")
    overall_feedback: Optional[str] = Field(None, description="Overall feedback")
    recommendations: Optional[str] = Field(None, description="Recommendations (JSON)")
    interview_readiness_score: Optional[float] = Field(None, description="Interview readiness score")
    
    # Timestamps
    interview_date: datetime = Field(default_factory=datetime.utcnow)
    completed_date: Optional[datetime] = Field(None, description="Completion date")


# Error Models
class TheiaError(BaseModel):
    """Error response model"""
    error_type: str = Field(..., description="Type of error")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Voice-specific Models
class VoiceSessionConfig(BaseModel):
    """Voice session configuration"""
    sample_rate: int = Field(default=16000, description="Audio sample rate")
    channels: int = Field(default=1, description="Number of audio channels")
    format: str = Field(default="pcm16", description="Audio format")
    voice_model: str = Field(default="gpt-4o-realtime-preview-2024-10-01", description="OpenAI voice model")
    
    # Voice Activity Detection (VAD)
    vad_threshold: float = Field(default=0.5, description="Voice activity detection threshold (0.0-1.0)")
    silence_duration_ms: int = Field(default=700, description="Silence duration in milliseconds before turn ends")
    prefix_padding_ms: int = Field(default=300, description="Audio padding before speech detection in milliseconds")


class VoiceResponse(BaseModel):
    """Voice response from AI"""
    audio_data: bytes = Field(..., description="Audio response data")
    transcript: str = Field(..., description="Text transcript of response")
    is_question: bool = Field(default=False, description="Whether this is a question")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


