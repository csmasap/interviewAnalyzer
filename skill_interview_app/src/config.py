from __future__ import annotations

import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_timeout_seconds: int = 30
    openai_max_retries: int = 3
    openai_model: str = "gpt-4"

    # Salesforce Configuration
    salesforce_username: Optional[str] = None
    salesforce_password: Optional[str] = None
    salesforce_security_token: Optional[str] = None
    salesforce_domain: str = "login"

    # Application Configuration
    log_level: str = "INFO"
    environment: str = "dev"

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()