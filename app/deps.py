from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.salesforce_client import SalesforceClient
from app.services.opportunity_service import OpportunityDiscussedService
from app.services.agent_service import OpenAIAgentService
from app.services.fit_agent_service import OpenAIFitAgentService
from app.services.jobspy_service import JobSpyService
from app.services.workflow_service import CareerWorkflowService
from app.services.workflow_state_service import WorkflowStateService
from app.services.job_analyzer_service import JobAnalyzerService
from app.services.interview_service import InterviewService


@lru_cache(maxsize=1)
def get_salesforce_client() -> SalesforceClient:
    settings: Settings = get_settings()
    return SalesforceClient(settings=settings)


@lru_cache(maxsize=1)
def get_opportunity_service() -> OpportunityDiscussedService:
    return OpportunityDiscussedService(salesforce_client=get_salesforce_client())


@lru_cache(maxsize=1)
def get_agent_service() -> OpenAIAgentService:
    # This will raise at first use if OPENAI_API_KEY is not set
    return OpenAIAgentService(settings=get_settings())


@lru_cache(maxsize=1)
def get_fit_agent_service() -> OpenAIFitAgentService:
    # This will raise at first use if OPENAI_API_KEY is not set
    return OpenAIFitAgentService(settings=get_settings())


@lru_cache(maxsize=1)
def get_jobspy_service() -> JobSpyService:
    return JobSpyService(settings=get_settings())


@lru_cache(maxsize=1)
def get_workflow_service() -> CareerWorkflowService:
    return CareerWorkflowService(
        agent_service=get_agent_service(),
        fit_agent_service=get_fit_agent_service(),
        jobspy_service=get_jobspy_service(),
    )


@lru_cache(maxsize=1)
def get_workflow_state_service() -> WorkflowStateService:
    return WorkflowStateService()


@lru_cache(maxsize=1)
def get_job_analyzer_service() -> JobAnalyzerService:
    return JobAnalyzerService(settings=get_settings())


@lru_cache(maxsize=1)
def get_interview_service() -> InterviewService:
    return InterviewService(settings=get_settings())
