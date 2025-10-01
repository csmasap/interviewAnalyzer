from functools import lru_cache

from services.job_hunter.core.config import Settings, get_settings
from services.job_hunter.services.salesforce_client import SalesforceClient
from services.job_hunter.services.opportunity_service import OpportunityDiscussedService
from services.job_hunter.services.jobspy_service import JobSpyService


@lru_cache(maxsize=1)
def get_salesforce_client() -> SalesforceClient:
    settings: Settings = get_settings()
    return SalesforceClient(settings=settings)


@lru_cache(maxsize=1)
def get_opportunity_service() -> OpportunityDiscussedService:
    return OpportunityDiscussedService(salesforce_client=get_salesforce_client())


@lru_cache(maxsize=1)
def get_jobspy_service() -> JobSpyService:
    return JobSpyService(settings=get_settings())
