from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.google_pse_service import get_sample_jobs
from app.core.config import get_settings
from app.services.salesforce_client import SalesforceClient

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

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