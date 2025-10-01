import os
import json
import logging
import asyncio
import pandas as pd
from jobspy import scrape_jobs
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

# Lazy import for google.generativeai to avoid crashing app when package or key is missing
_genai = None
def _ensure_genai():
    global _genai
    if _genai is not None:
        return _genai
    try:
        import google.generativeai as genai  # type: ignore
    except Exception as e:
        logger.error("google-generativeai not available: %s", e)
        return None
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set; AI-assisted sample jobs will be unavailable.")
        return None
    try:
        genai.configure(api_key=api_key)
        _genai = genai
        return _genai
    except Exception as e:
        logger.error("Failed to configure google-generativeai: %s", e)
        return None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env file (robust search)
load_dotenv(find_dotenv())

# Gemini configuration is now lazy; missing key no longer crashes app startup

async def _extract_skills_with_ai(resume_txt: str, ai_summary: str, screening_transcript: str) -> dict:
    """
    Uses Gemini to extract skills, now performing a holistic analysis of the resume,
    interview transcript, and interview summary.
    """
    genai = _ensure_genai()
    if genai is None:
        return {"skills": [], "location": None}
    model = genai.GenerativeModel('gemini-2.5-pro')

    # --- Start of Prompt Modification ---
    # Build additional context sections ONLY if the data exists
    additional_context = ""
    if ai_summary:
        additional_context += f"""
        **Interview Analysis (Context and Interpretation):**
        ---
        {ai_summary}
        ---
        """
    if screening_transcript:
        additional_context += f"""
        **Interview Transcript (Raw Questions and Answers):**
        ---
        {screening_transcript}
        ---
        """

    prompt = f"""
   You are a seasoned technical recruiter and career analyst. Your task is to perform a holistic analysis of a candidate using three sources: their resume, an AI-generated analysis of their interview answers, and the raw interview transcript (Q&A).

    Your goal is to identify the candidate's 7 most marketable skills by following these critical steps:

    1.  **Synthesize All Sources**: Do not treat the documents in isolation. Cross-reference the skills and experiences listed on the **resume** with the detailed answers provided in the **interview transcript**. Use the **interview analysis** to understand the context and quality of their answers.

    2.  **Prioritize Proven Skills**: Give the highest weight to skills that are clearly and confidently explained in the **interview transcript**. A skill merely listed on the resume is a claim; a skill well-articulated in an interview is proof.

    3.  **Validate with the Transcript**: Use the raw Q&A in the transcript to validate the claims made in the resume. For example, if the resume lists "Expert in Apex," look for a question about Apex in the transcript and evaluate if the answer demonstrates true expertise.

    4.  **Use the Analysis for Nuance**: Leverage the **interview analysis** to identify strategic thinking, problem-solving ability, and communication skills that might not be obvious from the resume alone.

    Based on this comprehensive, cross-referenced analysis, identify the top 7 most impactful and proven skills. Also, extract the candidate's location from the resume.

    Interview Transcript: {screening_transcript}
    Interview Analysis: {ai_summary} 

    **Resume Text (Experience History):**
    ---
    {resume_txt}
    ---

    Return your answer **ONLY** as a single, valid JSON object with two keys: "skills" (a list of 7 strings) and "location".
    """
    # --- End of Prompt Modification ---

    try:
        response = await model.generate_content_async(prompt)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(json_text)
    except Exception as e:
        logger.error(f"An error occurred during AI skill extraction: {e}")
        return {"skills": [], "location": None}

async def _generate_search_query_with_ai(skills: list) -> str:
    """
    Uses Gemini to build a smart Boolean search query from a list of skills.
    """
    if not skills:
        return ""
        
    genai = _ensure_genai()
    if genai is None:
        return ""
    model = genai.GenerativeModel('gemini-2.5-pro')
    prompt = f"""
    You are an expert technical sourcer and a master of crafting advanced Boolean search queries for platforms like LinkedIn and Indeed.

    Your task is to convert a list of a candidate's skills into a highly effective Boolean search query that accurately matches their core competencies **and executive seniority level.**

    Follow this three-part structure:
    **(Senior Job Titles) AND (Core Function & Platform) AND (Supporting Skills & Technologies)**

    1.  **Infer Role and Seniority**:
        * Analyze the input skills and titles. If skills include "Team Leadership," "Management," "Strategy," or "Forecasting," and the implied experience is 8+ years, the target is a senior leadership role.
        * **Crucially, use appropriate senior titles. Instead of "Senior," use leadership titles like "Director", "Head of", "VP", or "Manager" enclosed in quotes.**

    2.  **Create the Job Title Group**: Create a parenthesized group with relevant senior job title variations using OR. Examples: ("Director of Sales Operations" OR "Head of Revenue Operations").

    3.  **Create the Core Group (Function AND Platform)**: This is the most important part.
        * Identify the primary **job function** (e.g., "Sales Operations", "Revenue Operations").
        * Identify the primary **technology platform** (e.g., "Salesforce").
        * Combine these two critical components with AND in a parenthesized group. Example: ("Sales Operations" AND Salesforce). This ensures the job is not just about the tool, but the strategic function itself.

    4.  **Create the Supporting Skills Group**: Use the remaining skills (automation tools, specific strategies, etc.) to create a final parenthesized group, joined by OR.

    5.  **Assemble the Query**: Combine the three groups with AND. Ensure any multi-word items are enclosed in double quotes "".

    ---
    **Example 1: (Corrected Developer Query)**
    **Input Skills:** ["Apex", "LWC", "Salesforce Flow", "JavaScript", "REST API", "Git", "SQL"]
    **Resulting Query:** ("Salesforce Developer" OR "Salesforce Engineer") AND (Apex AND LWC) AND ("Salesforce Flow" OR JavaScript OR "REST API" OR SQL)

    **Example 2: (NEW Leadership Query - Highly Relevant to Your Case)**
    **Input Skills:** ["Sales Operations Management", "Revenue Forecasting", "Salesforce", "Go-to-Market Strategy", "Sales Automation", "Team Leadership", "Apollo.io"]
    **Resulting Query:** ("Director of Sales Operations" OR "Head of Sales Operations" OR "Sales Operations Manager") AND ("Revenue Operations" AND Salesforce) AND ("Go-to-Market Strategy" OR "Sales Automation" OR Forecasting OR Apollo.io)
    ---

    Return your answer **ONLY** as a single, valid JSON object with one key: "query".

    **Input Skills:**
    {skills}
    """
    try:
        response = await model.generate_content_async(prompt)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(json_text)
        return data.get("query", "")
    except Exception as e:
        logger.error(f"An error occurred during AI query generation: {e}")
        return ""

async def build_ai_query(resume_txt: str | None, ai_summary: str | None, screening_transcript: str | None) -> dict:
    """
    Build an AI-generated Boolean search query (and location/country) from available inputs.

    Returns: { "query": str, "location": Optional[str], "country_code": str }
    """
    resume_txt = resume_txt or ""
    ai_summary = ai_summary or ""
    screening_transcript = screening_transcript or ""

    logger.info("Stage 2: AI extraction start (resume_len=%d, summary_len=%d, transcript_len=%d)", len(resume_txt), len(ai_summary), len(screening_transcript))
    extracted_info = await _extract_skills_with_ai(resume_txt, ai_summary, screening_transcript)
    location = extracted_info.get("location")
    skills = extracted_info.get("skills", [])
    logger.info("Stage 2: AI extraction complete (skills=%d, location=%s)", len(skills), location or "")

    query = await _generate_search_query_with_ai(skills)
    logger.info("Stage 2: AI query generated (len=%d)", len(query))

    country_code = "usa"
    try:
        if location and isinstance(location, str) and "colombia" in location.lower():
            country_code = "colombia"
    except Exception:
        pass

    return {
        "query": query,
        "location": location,
        "country_code": country_code,
    }

async def _run_single_scrape(search_term: str, location: str, country_code: str) -> pd.DataFrame:
    """
    Runs one targeted jobspy scrape using the AI-generated query.
    """
    logger.info(f"🚀 Performing single scrape with AI-generated query in '{location}'")
    logger.info(f"Query: {search_term}")
    try:
        # Prefer extracted location when available; fallback to 'united states'
        normalized_location = (location or '').strip() or 'united states'
        jobs_df = await asyncio.to_thread(
            scrape_jobs,
            site_name=["linkedin", "indeed"],
            search_term=search_term,
            location=normalized_location,
            results_wanted=10,
            hours_old=168,
            country_indeed=country_code
        )
        logger.info(f"✅ Finished single scrape.")
        return jobs_df if jobs_df is not None else pd.DataFrame()
    except Exception as e:
        logger.error(f"Scrape failed for query '{search_term}': {e}", exc_info=True)
        return pd.DataFrame()
    
async def get_sample_jobs(resume_txt: str, ai_summary: str, screening_transcript: str):
    logger.info("📄 Step 1/3: Analyzing resume to extract key skills...")
    extracted_info = await _extract_skills_with_ai(resume_txt, ai_summary, screening_transcript)
    
    location = extracted_info.get("location", "Cali, Colombia")
    target_skills = extracted_info.get("skills", [])
    
    if not target_skills:
        logger.warning("No skills were extracted, cannot proceed.")
        return []

    logger.info(f"AI Extracted Skills: {target_skills}")

    logger.info("🤖 Step 2/3: Generating smart search query with AI...")
    search_query = await _generate_search_query_with_ai(target_skills)

    if not search_query:
        logger.warning("AI failed to generate a search query.")
        return []

    country_code = "colombia" if "colombia" in location.lower() else "usa"

    logger.info("⚡ Step 3/3: Executing single targeted scrape...")
    jobs_df = await _run_single_scrape(search_query, location, country_code)

    if jobs_df.empty:
        logger.warning("Scrape returned no jobs for the generated query.")
        return []

    logger.info(f"🎯 Found {len(jobs_df)} relevant jobs.")

    # Format the final output
    jobs_renamed = jobs_df[['title', 'company', 'location', 'job_url']].rename(columns={'job_url': 'link'})
    job_postings = jobs_renamed.to_dict('records')
    
    return job_postings