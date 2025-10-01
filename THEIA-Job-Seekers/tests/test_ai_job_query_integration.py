import os
import pytest

from services.job_hunter.core.config import get_settings
from services.job_hunter.services.salesforce_client import SalesforceClient
from services.job_hunter.services.google_pse_service import build_ai_query


OD_ID = "a0bPM00000X2FXpYAN"


def _require_env(var_names):
    missing = [name for name in var_names if not os.getenv(name)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ai_builds_query_from_opportunity_discussed():
    """
    Integration test:
    - Loads Salesforce record by hard-coded Opportunity Discussed Id
    - Extracts resume text and AI interview summary
    - Builds AI Boolean query with google_pse_service
    """
    _require_env([
        "SALESFORCE_USERNAME",
        "SALESFORCE_PASSWORD",
        "SALESFORCE_SECURITY_TOKEN",
        "GOOGLE_API_KEY",
    ])

    settings = get_settings()
    sf = SalesforceClient(settings)

    # 1) Fetch Opportunity Discussed record
    raw = sf.query_opportunity_discussed_by_id(OD_ID)
    assert raw is not None, "Salesforce returned no record for the given OD Id"

    # 2) Extract inputs for AI query builder
    candidate_rel = raw.get("TR1__Candidate__r") or {}
    resume_txt = candidate_rel.get("Candidate_s_Resume_TXT__c") or ""
    ai_summary = raw.get("AI_Interview_Summary__c") or ""

    # 3) Build AI-generated query
    ai = await build_ai_query(resume_txt, ai_summary, None)

    assert isinstance(ai, dict), "AI result should be a dict"
    assert ai.get("query"), f"AI did not produce a query: {ai}"
    # Optional sanity checks
    assert "(" in ai["query"], "Query should look like a Boolean expression"

    # For visibility in CI logs
    print("AI Query:", ai["query"])  # noqa: T201
    print("Location:", ai.get("location"))  # noqa: T201
    print("Country Code:", ai.get("country_code"))  # noqa: T201


