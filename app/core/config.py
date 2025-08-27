from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # App
    environment: str = Field(default="dev", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Salesforce (optional at startup; validated when connecting)
    salesforce_username: Optional[str] = Field(default=None, alias="SALESFORCE_USERNAME")
    salesforce_password: Optional[str] = Field(default=None, alias="SALESFORCE_PASSWORD")
    salesforce_security_token: Optional[str] = Field(default=None, alias="SALESFORCE_SECURITY_TOKEN")
    # 'login' for production, 'test' for sandbox
    salesforce_domain: str = Field(default="login", alias="SALESFORCE_DOMAIN")

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(default=None, alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_timeout_seconds: int = Field(default=60, alias="OPENAI_TIMEOUT_SECONDS")
    openai_max_retries: int = Field(default=2, alias="OPENAI_MAX_RETRIES")

    # JobSpy
    jobspy_sites_csv: str = Field(default="indeed,linkedin", alias="JOBSPY_SITES")
    jobspy_results_wanted: int = Field(default=20, alias="JOBSPY_RESULTS_WANTED")
    jobspy_hours_old: int = Field(default=72, alias="JOBSPY_HOURS_OLD")
    jobspy_country_indeed: str = Field(default="USA", alias="JOBSPY_COUNTRY_INDEED")
    jobspy_timeout_seconds: int = Field(default=30, alias="JOBSPY_TIMEOUT_SECONDS")
    
    # Workflow
    workflow_timeout_seconds: int = Field(default=300, alias="WORKFLOW_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def jobspy_sites(self) -> list[str]:
        return [s.strip() for s in self.jobspy_sites_csv.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
