## Interview Analyzer API (Salesforce-connected)

A FastAPI web service that connects to Salesforce and retrieves `TR1__Opportunity_Discussed__c` records by Id, returning a curated set of fields.

### Features
- FastAPI for a modern, performant Python web API
- Layered, scalable architecture (routers → services → clients)
- Config via environment variables with `pydantic-settings`
- Salesforce connectivity using `simple-salesforce`
- Production-ready logging
- Basic test scaffold
- **NEW: AI-powered interview service with two-stage questioning**

### Endpoints
- `GET /api/v1/opportunity-discussed/{record_id}`
  - Fetches a `TR1__Opportunity_Discussed__c` by Id and returns key fields.
  - Response fields are normalized (Pythonic) for API ergonomics.

- **NEW: Interview Service Endpoints**
  - `POST /api/v1/interview/{record_id}/start` - Start AI interview, generate position and yes/no questions
  - `POST /api/v1/interview/{interview_id}/yes-no-answers` - Submit yes/no answers, get open-ended questions
  - `POST /api/v1/interview/{interview_id}/complete` - Complete interview, save to Salesforce
  - `GET /api/v1/interview/{interview_id}/status` - Get interview status

- **NEW: Interview UI**
  - `GET /interview` - Interactive interview interface

Example response:
```json
{
  "id": "a0Nxx0000000001",
  "name": "Sample Name",
  "candidate": {
    "name": "John Doe",
    "email": "john.doe@example.com"
  },
  "sum_scorecard_evaluation": 42.5,
  "reason_capable_of": "Reason text",
  "candidate_interviews_summary": "Summary text",
  "salary_expectations": "100k",
  "scorecard_full_candidate_report": "Report text or URL",
  "ai_interview_summary": "Summary",
  "interview_candidate_score": 8.9,
  "interview_candidate_feedback": "Feedback text"
}
```

### Salesforce fields queried
- Id
- Name
- TR1__Candidate__r.Name
- TR1__Candidate__r.Email
- TR1__Candidate__r.Candidate_s_Resume_TXT__c
- Sum_ScoreCard_Evaulation__c
- Reason_Capable_of__c
- Candidate_Interviews_Summary__c
- Salary_Expectations__c
- Scorecard_Full_Candidate_Report__c
- AI_Interview_Summary__c
- Interview_Candidate_Score__c
- Interview_Candidate_Feedback__c

### **NEW: AI Interview Service**

The interview service provides a two-stage AI-powered interview process:

#### Stage 1: Initial Screening
- Analyzes candidate resume using OpenAI
- Generates realistic job position title
- Creates 3 relevant yes/no screening questions

#### Stage 2: Detailed Assessment
- Based on yes/no answers, generates 2 open-ended questions
- Questions are tailored to the candidate's background and responses
- Creates comprehensive interview summary

#### Salesforce Integration
- Creates or updates `AI_Interview__c` records
- Links to `TR1__Opportunity_Discussed__c` via `Opportunity_Discussed__c` field
- Stores interview summary in `Interview_Summary__c` field

### Project structure
```
app/
  api/routers/
    opportunity_discussed.py
    interview.py          # NEW: Interview endpoints
  core/config.py
  core/logging_config.py
  deps.py
  main.py
  services/
    salesforce_client.py
    opportunity_service.py
    interview_service.py  # NEW: Interview logic
  models/
    schemas.py           # Updated with interview schemas
  templates/
    job_analyzer.html
    workflow.html
    interview.html       # NEW: Interview UI
```

### Setup
1. Python 3.10+
2. Create a virtual environment and install dependencies:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
3. Configure environment variables (copy `.env.example` to `.env` and fill in values):
```ini
SALESFORCE_USERNAME=your-username
SALESFORCE_PASSWORD=your-password
SALESFORCE_SECURITY_TOKEN=your-token
SALESFORCE_DOMAIN=login  # or 'test' for sandbox
OPENAI_API_KEY=your-openai-api-key  # Required for interview service
```

### Run locally
```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Visit `http://localhost:8000/docs` for interactive API docs.

### **NEW: Interview Interface**
- Visit `http://localhost:8000/interview` for the interactive interview UI
- Pass a `record_id` parameter to start with a specific Salesforce record
- Example: `http://localhost:8000/interview?record_id=a0N123456789012`

### Testing
```powershell
pytest -q
```

### Notes
- This service uses the username/password + security token flow via `simple-salesforce` for simplicity. For production, consider OAuth 2.0 flows and a secrets manager.
- Input validation restricts the Salesforce Id to 15–18 alphanumeric characters.
- **NEW: The interview service requires a valid OpenAI API key to function.**
- **NEW: Interview sessions are stored in memory by default. For production, consider using Redis or a database for session persistence.**
