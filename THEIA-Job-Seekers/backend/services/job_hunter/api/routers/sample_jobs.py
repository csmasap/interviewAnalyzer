from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from services.job_hunter.services.google_pse_service import get_sample_jobs
from services.job_hunter.core.config import get_settings
from services.job_hunter.services.salesforce_client import SalesforceClient

router = APIRouter()
from pathlib import Path
# Resolve to .../backend/services/job_hunter/templates
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))

@router.get("/sample-jobs", response_class=HTMLResponse)
async def sample_jobs(request: Request, record_id: str):
    settings = get_settings()
    sf_client = SalesforceClient(settings)
    contact = sf_client.query_contact_by_id(record_id)
    resume_txt = contact.get("Candidate_s_Resume_TXT__c") if contact else None

    opportunities = contact.get("TR1__Opportunities_Discussed__r")
    if opportunities and opportunities.get("records"):
        # Get the first related opportunity record
        first_opportunity = opportunities["records"][0]
        ai_summary = first_opportunity.get("AI_Interview_Summary__c", "")
        screening_transcript = first_opportunity.get("Screening_Transcript__c", "")
    
    jobs = await get_sample_jobs(resume_txt, ai_summary, screening_transcript)
    
    return templates.TemplateResponse(
        "sample_jobs.html",
        {"request": request, "jobs": jobs, "record_id": record_id}
    )


@router.get("/sample-jobs.json", response_class=JSONResponse)
async def sample_jobs_json(record_id: str = Query(..., description="Salesforce Contact Id (003...)") ):
    settings = get_settings()
    sf_client = SalesforceClient(settings)
    contact = sf_client.query_contact_by_id(record_id)
    resume_txt = contact.get("Candidate_s_Resume_TXT__c") if contact else None

    ai_summary = ""
    screening_transcript = ""
    opportunities = contact.get("TR1__Opportunities_Discussed__r") if contact else None
    if opportunities and opportunities.get("records"):
        first_opportunity = opportunities["records"][0]
        ai_summary = first_opportunity.get("AI_Interview_Summary__c", "")
        screening_transcript = first_opportunity.get("Screening_Transcript__c", "")

    jobs = await get_sample_jobs(resume_txt, ai_summary, screening_transcript)
    return JSONResponse(content=jobs)