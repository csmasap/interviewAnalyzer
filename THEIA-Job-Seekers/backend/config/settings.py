"""
THEIA Interview Prep System Settings
Centralized configuration management using Pydantic Settings.
"""

import os
from typing import List, Optional
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import validator, Field


class Settings(BaseSettings):
    """Application settings with environment-based configuration"""
    
    # Application settings
    APP_NAME: str = "THEIA Interview Prep System"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # OpenAI settings
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for Realtime API")
    OPENAI_REALTIME_MODEL: str = "gpt-4o-realtime-preview-2024-10-01"
    
    # Google Cloud settings
    GOOGLE_CLOUD_PROJECT_ID: str = Field(default="", description="Google Cloud Project ID")
    GOOGLE_CLOUD_LOCATION: str = Field(default="us-central1", description="Google Cloud region")
    # Note: In Cloud Run, we use default service account, not JSON file
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(default=None, description="Path to GCP service account JSON (local dev only)")
    
    # Vertex AI settings
    VERTEX_AI_MODEL: str = "gemini-2.5-pro"  # Primary model for complex tasks
    VERTEX_AI_MODEL_FAST: str = "gemini-2.5-flash"  # Fast model for simple tasks
    VERTEX_AI_LOCATION: str = "us-central1"
    
    # Google Search API settings (for ISA_Researcher web search)
    GOOGLE_CSE_ID: str = Field(default="", description="Google Custom Search Engine ID")
    GOOGLE_API_KEY: str = Field(default="", description="Google API Key for Custom Search")
    
    @validator("GOOGLE_CLOUD_PROJECT_ID", pre=True)
    def set_project_id(cls, v):
        """Use GOOGLE_CLOUD_PROJECT if GOOGLE_CLOUD_PROJECT_ID is not set"""
        if not v:
            # Try multiple environment variable names
            project_id = (
                os.getenv("GOOGLE_CLOUD_PROJECT") or 
                os.getenv("VERTEX_PROJECT_ID") or 
                os.getenv("GCP_PROJECT") or
                ""
            )
            return project_id
        return v
    
    # Auth0 settings
    AUTH0_DOMAIN: str = Field(default="", description="Auth0 domain")
    AUTH0_AUDIENCE: str = Field(default="", description="Auth0 API audience")
    AUTH0_CLIENT_ID: str = Field(default="", description="Auth0 client ID")
    
    # THEIA JWT settings
    THEIA_JWT_ISSUER: str = Field(default="theia", description="JWT issuer")
    THEIA_JWT_AUDIENCE: str = Field(default="theia-clients", description="JWT audience")
    THEIA_JWT_SECRET: str = Field(default="please_change_and_store_securely", description="JWT secret key")
    THEIA_JWT_TTL_SECONDS: int = Field(default=7200, description="JWT time to live in seconds")
    
    # Salesforce settings
    SF_USERNAME: str = Field(default="", description="Salesforce username")
    SF_PASSWORD: str = Field(default="", description="Salesforce password")
    SF_SECURITY_TOKEN: str = Field(default="", description="Salesforce security token")
    SF_DOMAIN: str = "login"
    SALESFORCE_API_VERSION: str = "v58.0"
    
    # Redis settings (for session management and Celery)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None
    
    # Celery settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",  # React development server
        "http://127.0.0.1:3000",
        "http://localhost:8000",  # FastAPI server
        "http://127.0.0.1:8000",
        # Add production URLs when deployed
    ]
    
    # WebSocket settings
    MAX_WEBSOCKET_CONNECTIONS: int = 50  # Support for concurrent interviews
    WEBSOCKET_TIMEOUT: int = 300  # 5 minutes
    WEBSOCKET_PING_INTERVAL: int = 30
    WEBSOCKET_PING_TIMEOUT: int = 300  # 5 minutes
    
    # Session settings
    SESSION_TTL: int = 7200  # 2 hours for interview sessions
    MAX_CONCURRENT_SESSIONS: int = 50  # Support for 20-50 concurrent interviews
    SESSION_CLEANUP_INTERVAL: int = 300  # 5 minutes
    
    # Memory optimization settings
    MAX_MEMORY_PERCENT: float = 80.0
    MEMORY_CLEANUP_THRESHOLD: float = 70.0
    MEMORY_MONITOR_INTERVAL: int = 30  # seconds
    
    # Interview settings
    MAX_INTERVIEW_DURATION: int = 3600  # 1 hour
    MAX_QUESTIONS: int = 10  # Maximum questions per interview
    MAX_QUESTION_LENGTH: int = 1000
    MAX_ANSWER_LENGTH: int = 5000
    
    # Agent timeout settings (in seconds) - Doubled for better reliability
    AGENT_TIMEOUT_DEFAULT: int = 60
    AGENT_TIMEOUT_RESEARCH: int = 120  # ISA_Researcher needs more time for web research
    AGENT_TIMEOUT_EVALUATION: int = 90  # ISA_Evaluator needs more time for analysis
    AGENT_TIMEOUT_DETECTION: int = 60   # ISA_Detector timeout
    AGENT_TIMEOUT_QUESTIONING: int = 120  # ISA_Questioner timeout
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    ENABLE_SQL_LOGGING: bool = False
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        """Validate environment setting"""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v
    
    @validator("DEBUG", pre=True)
    def validate_debug(cls, v, values):
        """Set debug based on environment if not explicitly set"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        if "ENVIRONMENT" in values:
            return values["ENVIRONMENT"] == "development"
        return False
    
    @validator("CELERY_BROKER_URL", pre=True)
    def set_celery_broker(cls, v, values):
        """Set Celery broker URL based on Redis URL if not explicitly set"""
        if v == "redis://localhost:6379/1" and "REDIS_URL" in values:
            redis_url = values["REDIS_URL"]
            # Replace database number for Celery
            if redis_url.endswith("/0"):
                return redis_url.replace("/0", "/1")
        return v
    
    @validator("CELERY_RESULT_BACKEND", pre=True)
    def set_celery_result_backend(cls, v, values):
        """Set Celery result backend based on Redis URL if not explicitly set"""
        if v == "redis://localhost:6379/1" and "REDIS_URL" in values:
            redis_url = values["REDIS_URL"]
            # Replace database number for Celery results
            if redis_url.endswith("/0"):
                return redis_url.replace("/0", "/2")
        return v
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_allowed_origins(cls, v):
        """Allow comma-separated string or JSON array for ALLOWED_ORIGINS in .env."""
        if isinstance(v, str):
            s = v.strip()
            # JSON array case
            if s.startswith("[") and s.endswith("]"):
                try:
                    import json as _json
                    loaded = _json.loads(s)
                    if isinstance(loaded, list):
                        return loaded
                except Exception:
                    pass
            # Comma-separated values
            if "," in s:
                return [item.strip() for item in s.split(",") if item.strip()]
            # Single origin string
            return [s] if s else []
        return v
    
    class Config:
        env_file = "../.env"  # Look for .env in parent directory
        env_file_encoding = "utf-8"
        case_sensitive = True


class DevelopmentSettings(Settings):
    """Development-specific settings"""
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    
    # More relaxed limits for development
    MAX_WEBSOCKET_CONNECTIONS: int = 20
    WEBSOCKET_TIMEOUT: int = 1200  # 20 minutes
    MAX_CONCURRENT_SESSIONS: int = 15


class ProductionSettings(Settings):
    """Production-specific settings"""
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Production optimizations
    MAX_WEBSOCKET_CONNECTIONS: int = 50
    WEBSOCKET_TIMEOUT: int = 300  # 5 minutes
    MAX_CONCURRENT_SESSIONS: int = 50


@lru_cache()
def get_settings() -> Settings:
    """
    Get application settings based on environment.
    Uses LRU cache to avoid re-reading environment variables.
    """
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    if environment == "production":
        print("🔧 Using production settings")
        return ProductionSettings()
    elif environment == "development":
        print("🔧 Using development settings")
        return DevelopmentSettings()
    else:
        print(f"🔧 Using default settings for environment: {environment}")
        return Settings()


# Export settings instance
settings = get_settings()
