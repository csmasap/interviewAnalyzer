import asyncio
import os
import pytest


@pytest.mark.asyncio
async def test_isa_researcher_websearch_smoke():
    """
    Smoke test: ensure ISA_Researcher can execute a web-enabled generation path
    (Enterprise Web Search via google.generativeai or Vertex google_search fallback)
    and return a non-empty string without raising.

    This is intentionally lenient: it verifies connectivity and basic execution,
    not quality of grounding or JSON structure. Inspect logs to see which path
    was taken (enterprise, vertex, or plain fallback).
    """
    # Skip if project is obviously not configured at all
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not project_id and not api_key:
        pytest.skip("Neither GOOGLE_CLOUD_PROJECT_ID nor GOOGLE_API_KEY configured")

    # Import via package path; ensure backend dir is on sys.path
    import sys
    backend_dir = os.path.join(os.getcwd(), "external", "THEIA-Job-Seekers", "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from theia_agents.isa_researcher import ISAResearcher  # type: ignore
    researcher = ISAResearcher()

    # Minimal prompt that should work with any of the grounded/ungrounded paths
    prompt = (
        "You are running a smoke test for ISA_Researcher. Using web search if available, "
        "produce concise JSON about interview practices for 'Ramp' Customer Success Manager. "
        "Return ONLY JSON with fields company_info, interview_insights, common_questions, "
        "interview_style, market_intelligence, research_confidence, sources_found."
    )

    # Call the web-enabled generation path directly
    text = await researcher._generate_research_with_web(prompt)

    assert isinstance(text, str)
    assert len(text.strip()) > 0

