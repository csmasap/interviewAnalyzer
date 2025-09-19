import aiohttp
import os
import json
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

async def get_sample_jobs(resume_txt: str):
    """
    This function should use Google PSE to find 3 recent job postings from LinkedIn or Indeed that closely match the candidate's experience and skills.
    For each job, it should return a JSON object with 'title', 'company', and 'link'.
    """
    api_key = "AIzaSyAqYcaJgd8yN1592cKCUR6Aik0LklYMB1o"
    cx = "e7c3b1a33e73d40fd"
    search_query = 'site:linkedin.com/jobs/view/ "Salesforce Developer"'
    url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={search_query}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    job_postings = []
                    for item in data.get("items", [])[:3]:  # Take the first 3 jobs
                        job_postings.append({
                            "title": item.get("title", ""),
                            "company": item.get("displayLink", ""),  # Using displayLink as company for now
                            "link": item.get("link", "")
                        })
                    return job_postings
                else:
                    print(f"Error: {response.status} - {await response.text()}")
                    return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []


