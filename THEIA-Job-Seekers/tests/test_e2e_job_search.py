import os
import pytest

from services.job_hunter.core.config import get_settings
from services.job_hunter.services.salesforce_client import SalesforceClient
from services.job_hunter.services.opportunity_service import OpportunityDiscussedService
from services.job_hunter.services.google_pse_service import build_ai_query
from services.job_hunter.services.jobspy_service import JobSpyService


OD_ID = "a0bPM00000X2FXpYAN"


def _require_env(var_names):
    missing = [name for name in var_names if not os.getenv(name)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_job_search_with_ai_query():
    """
    E2E test:
    - Fetch OD record by Id
    - Build AI Boolean query (and location) from resume + AI summary
    - Run JobSpyService search with that query and assert we get results
    """
    _require_env([
        "SALESFORCE_USERNAME",
        "SALESFORCE_PASSWORD",
        "SALESFORCE_SECURITY_TOKEN",
        "GOOGLE_API_KEY",
    ])

    settings = get_settings()
    sf_client = SalesforceClient(settings)
    od_service = OpportunityDiscussedService(sf_client)

    # 1) Get normalized domain record
    record = od_service.get_by_id(OD_ID)
    assert record is not None, "Opportunity Discussed not found"

    # 2) Build AI query
    resume_txt = record.candidate.resume_text if (record.candidate and record.candidate.resume_text) else ""
    ai_summary = record.ai_interview_summary or ""
    ai = await build_ai_query(resume_txt, ai_summary, None)
    assert ai.get("query"), f"AI did not produce a query: {ai}"

    # 3) Execute JobSpy search
    jobspy = JobSpyService(settings)
    override = {
        "search_term": ai.get("query"),
        "location": ai.get("location"),
        "results_wanted": 5,
        "hours_old": 168,
    }
    cc = ai.get("country_code")
    if cc:
        override["country_indeed"] = str(cc).upper()

    jobs = jobspy.search(record, override=override)
    assert isinstance(jobs, list), "Jobs should be a list of dicts"
    assert len(jobs) > 0, "Expected at least one job result"

    # Basic shape checks
    first = jobs[0]
    assert "title" in first and "company" in first and "job_url" in first


