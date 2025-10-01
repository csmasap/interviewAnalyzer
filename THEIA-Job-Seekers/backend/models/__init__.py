"""Models module for THEIA Interview Prep System"""

from .theia_models import (
    # Enums
    InterviewMode,
    InterviewPhase,
    InterviewStatus,
    
    # Input Models
    InterviewRequest,
    UserMessage,
    VoiceMessage,
    
    # Agent Output Models
    ResearchOutput,
    SkillsDetectionOutput,
    QuestionGenerationOutput,
    EvaluationOutput,
    PreparedInterviewContext,
    
    # Session Models
    InterviewSession,
    InterviewProgress,
    
    # WebSocket Models
    WebSocketMessage,
    StatusMessage,
    QuestionMessage,
    AIResponseMessage,
    EvaluationMessage,
    
    # Salesforce Models
    SalesforceContact,
    TheiaInterviewRecord,
    
    # Voice Models
    VoiceSessionConfig,
    VoiceResponse,
    
    # Error Models
    TheiaError,
)

__all__ = [
    # Enums
    "InterviewMode",
    "InterviewPhase", 
    "InterviewStatus",
    
    # Input Models
    "InterviewRequest",
    "UserMessage",
    "VoiceMessage",
    
    # Agent Output Models
    "ResearchOutput",
    "SkillsDetectionOutput", 
    "QuestionGenerationOutput",
    "EvaluationOutput",
    "PreparedInterviewContext",
    
    # Session Models
    "InterviewSession",
    "InterviewProgress",
    
    # WebSocket Models
    "WebSocketMessage",
    "StatusMessage",
    "QuestionMessage",
    "AIResponseMessage", 
    "EvaluationMessage",
    
    # Salesforce Models
    "SalesforceContact",
    "TheiaInterviewRecord",
    
    # Voice Models
    "VoiceSessionConfig",
    "VoiceResponse",
    
    # Error Models
    "TheiaError",
]


