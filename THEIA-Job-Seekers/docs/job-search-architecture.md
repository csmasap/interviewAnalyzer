## Job Search Architecture and Implementation Guide

This document explains how job search works in this project, how the pieces fit together, and how to replicate or extend the system. It covers both job search paths:

- Heuristic JobSpy search driven by Salesforce data
- AI-assisted search using Gemini to extract skills and craft a Boolean query, then JobSpy for scraping

### At a glance
- **Salesforce** provides candidate/interview data.
- **Opportunity normalization** maps raw Salesforce to a domain model.
- **JobSpyService** infers a search title from candidate data, builds JobSpy params, runs scraping, and trims results.
- **Google PSE service** uses Gemini to extract skills/location and generate a Boolean query for one focused JobSpy scrape.
- **Routers** expose endpoints and orchestrate the flow; **Workflow** integrates job search as a final step.
- **Config** centralizes JobSpy and AI settings through environment variables.


## Components

### Salesforce client and domain mapping
- `app/services/salesforce_client.py`
  - Thread-safe lazy connection via `simple-salesforce`.
  - Key queries:
    - `query_opportunity_discussed_by_id(record_id)` returns fields like candidate relations, interview summaries, and reports.
    - `query_opportunity_discussed_by_candidate(candidate_id, limit)` fetches recent discussions for a candidate.
    - `query_contact_by_id(contact_id)` returns a Contact with `Candidate_s_Resume_TXT__c` and a subquery of related opportunities (includes `AI_Interview_Summary__c`, `Screening_Transcript__c`).
- `app/services/opportunity_service.py`
  - Converts raw Salesforce dicts into `app/models/schemas.py:OpportunityDiscussed`.
  - Normalizes strings/floats and extracts the related `Candidate` with `resume_text`.

### Heuristic JobSpy search
- `app/services/jobspy_service.py`
  - `_collect_text_fields(record)`: Aggregates name, summaries, feedback, reason_capable_of, and candidate resume text.
  - `_infer_title(record)`: Uses regex over the aggregated text to infer seniority (e.g., Senior, Lead) and role (e.g., Software Engineer, Data Scientist). Falls back to "Software Engineer".
  - `_build_search(record, override)`: Builds params for `jobspy.scrape_jobs`:
    - `site_name`: from `Settings.jobspy_sites` (parsed from `JOBSPY_SITES`).
    - `search_term`: inferred title.
    - `location`: `None` unless an override is passed.
    - `results_wanted`, `hours_old`, `country_indeed`: from settings.
  - `search(record, override)`: Calls `scrape_jobs(**params)` with a timeout guard; trims the DataFrame to a stable set of fields and returns a list of dicts.

### AI-assisted sample jobs (Gemini + JobSpy)
- `app/services/google_pse_service.py`
  - `_extract_skills_with_ai(resume_txt, ai_summary, screening_transcript)`: Uses Gemini to return `{ skills: [7], location }` from resume + interview context.
  - `_generate_search_query_with_ai(skills)`: Uses Gemini to craft an advanced Boolean query.
  - `_run_single_scrape(search_term, location, country_code)`: Performs one targeted `scrape_jobs` run (LinkedIn + Indeed) and returns a DataFrame.
  - `get_sample_jobs(resume_txt, ai_summary, screening_transcript)`: Orchestrates the three steps above and returns a minimal list of `{ title, company, location, link }`.

Notes:
- The AI path currently hardcodes `location='united states'` in `_run_single_scrape`; consider aligning with the extracted `location`.

### Routers and endpoints
- `app/api/routers/opportunity_discussed.py`
  - `GET /opportunity-discussed/{record_id}`: Returns normalized `OpportunityDiscussed`.
  - `GET /opportunity-discussed/{record_id}/jobs`:
    - Loads record via `OpportunityDiscussedService`.
    - Calls `JobSpyService.search(record, override={search_term, location, results_wanted, hours_old})`.
  - Workflow endpoints integrate job search at the final step (`jobs_complete`), defaulting to `results_wanted=3`.
- `app/api/routers/sample_jobs.py`
  - `GET /sample-jobs?record_id=...`:
    - Queries `SalesforceClient.query_contact_by_id(record_id)`.
    - Extracts `resume_txt`, and from the first related opportunity: `AI_Interview_Summary__c`, `Screening_Transcript__c`.
    - Calls `google_pse_service.get_sample_jobs()` and renders a Jinja template.

### Workflow integration
- `app/services/workflow_service.py`
  - As part of a multi-step career workflow (analysis, guidance, jobs), calls `JobSpyService.search(records[0], override={"results_wanted": 3})` and emits jobs as the final step.

### Dependency injection and config
- `app/deps.py` wires singletons via `@lru_cache`:
  - `get_salesforce_client()`, `get_opportunity_service()`, `get_jobspy_service()`, `get_workflow_service()`, etc.
- `app/core/config.py:Settings` (via `.env`):
  - JobSpy: `JOBSPY_SITES`, `JOBSPY_RESULTS_WANTED`, `JOBSPY_HOURS_OLD`, `JOBSPY_COUNTRY_INDEED`, `JOBSPY_TIMEOUT_SECONDS`.
  - OpenAI: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`.
  - Salesforce: `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN`, `SALESFORCE_DOMAIN`.
  - Gemini: requires `GOOGLE_API_KEY` (loaded by `google_pse_service.py`).


## Data flows

### Heuristic JobSpy path (OpportunityDiscussed → Jobs)
1. Request hits `GET /opportunity-discussed/{record_id}/jobs`.
2. `OpportunityDiscussedService.get_by_id()` calls `SalesforceClient.query_opportunity_discussed_by_id()`; result is normalized to `OpportunityDiscussed`.
3. `JobSpyService.search()`:
   - Gathers text and infers a title via regex (`Senior Software Engineer`, etc.).
   - Builds JobSpy params from settings (sites, recency, country) and optional overrides (e.g., location).
   - Calls `jobspy.scrape_jobs(**params)` with a timeout.
   - Trims the result DataFrame to selected fields and returns a list of dicts.

### AI-assisted path (Contact → Resume + Interview → Gemini → Jobs)
1. Request hits `GET /sample-jobs?record_id=...`.
2. `SalesforceClient.query_contact_by_id()` returns Contact with `Candidate_s_Resume_TXT__c` and first related opportunity (`AI_Interview_Summary__c`, `Screening_Transcript__c`).
3. `google_pse_service.get_sample_jobs()`:
   - Extracts `[skills]` and `location` via `_extract_skills_with_ai()`.
   - Builds a Boolean search string via `_generate_search_query_with_ai()`.
   - Runs a single scrape via `_run_single_scrape()` (LinkedIn, Indeed) and formats the minimal output.


## Endpoints and usage

### Heuristic JobSpy
```bash
curl -s "http://localhost:8000/opportunity-discussed/RECORD_ID/jobs"
```

Optional overrides:
```bash
curl -s "http://localhost:8000/opportunity-discussed/RECORD_ID/jobs?search_term=Senior%20Data%20Scientist&location=Seattle&results_wanted=25&hours_old=168"
```

### AI-assisted sample jobs
```bash
curl -s "http://localhost:8000/sample-jobs?record_id=CONTACT_ID"
```

### Workflow (jobs as final step)
1) Start and collect analysis (then submit career path, complete): see `opportunity_discussed.py` workflow endpoints.


## Configuration and environment

Create a `.env` (or provide environment variables) for:

- Salesforce
  - `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN`
  - `SALESFORCE_DOMAIN` ("login" for prod, "test" for sandbox)
- JobSpy defaults
  - `JOBSPY_SITES` (e.g., `indeed,linkedin`)
  - `JOBSPY_RESULTS_WANTED` (e.g., `20`), `JOBSPY_HOURS_OLD` (e.g., `72`), `JOBSPY_COUNTRY_INDEED` (e.g., `USA`)
  - `JOBSPY_TIMEOUT_SECONDS` (e.g., `30`)
- OpenAI (for analysis/guidance in the workflow)
  - `OPENAI_API_KEY`, `OPENAI_BASE_URL` (optional), `OPENAI_MODEL`
- Gemini (for AI-assisted sample jobs)
  - `GOOGLE_API_KEY`


## Running locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```
2. Start the API:
```bash
uvicorn app.main:app --reload
```
3. Verify health:
```bash
curl -s http://localhost:8000/healthz
```
4. Try job search endpoints (use valid Salesforce IDs and data):
   - Heuristic: `/opportunity-discussed/{record_id}/jobs`
   - AI-assisted: `/sample-jobs?record_id={contact_id}`


## Replicating the job search outcome

1. Ensure Salesforce has a Contact with resume text and a related Opportunity record with interview summary/transcript (AI path), or an `OpportunityDiscussed` record with rich fields (heuristic path).
2. Configure environment variables in `.env` (Salesforce, JobSpy, OpenAI, Gemini).
3. Run the service and call the endpoints as shown.
4. Adjust search parameters as needed:
   - Heuristic path: pass `search_term`, `location`, `results_wanted`, `hours_old` as query params.
   - AI path: improve resume/interview inputs to guide Gemini extraction.


## Extensibility and best practices

- **Location handling**: In the AI path, use the extracted `location` instead of the hardcoded `'united states'`. In the heuristic path, consider inferring location from resume or Salesforce.
- **Search quality**: Extend `_infer_title()` with additional regex patterns or a lightweight ML classifier for role/seniority detection.
- **Deduplication**: Add post-processing to dedupe jobs by URL/title/company.
- **Resilience**: Maintain generous timeouts and catch scraper exceptions (already done in `JobSpyService`). Consider retry/backoff if providers throttle.
- **Observability**: Keep structured logs of params and results; add metrics around result counts and error rates.
- **Security**: Do not log secrets; validate Salesforce IDs (already sanitized in `SalesforceClient`).


## Returned data shapes

- Heuristic JobSpy (`/opportunity-discussed/{record_id}/jobs`): list of dicts with fields like `site`, `title`, `company`, `location`, `date_posted`, `job_url`, `job_type`, `interval`, `min_amount`, `max_amount`, `currency`, `is_remote`, `job_level`, `job_function`, `description`.
- AI-assisted sample jobs (`/sample-jobs`): simplified list of `{ title, company, location, link }`.


## File index (for quick reference)
- `app/services/salesforce_client.py`: Salesforce access + SOQL.
- `app/services/opportunity_service.py`: Normalization to domain model.
- `app/services/jobspy_service.py`: Heuristic inference + JobSpy scrape + trimming.
- `app/services/google_pse_service.py`: Gemini skill extraction + query + single JobSpy scrape.
- `app/api/routers/opportunity_discussed.py`: Heuristic job search and workflow endpoints.
- `app/api/routers/sample_jobs.py`: AI-assisted sample jobs endpoint.
- `app/core/config.py`: Settings and environment.
- `app/deps.py`: Dependency injection.


