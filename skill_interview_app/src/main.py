from __future__ import annotations

import logging
from typing import Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .skill_interview_service import SkillInterviewService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Skill Interview App",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Global service instance
skill_interview_service = None


@app.on_event("startup")
async def on_startup() -> None:
    global skill_interview_service
    settings = get_settings()
    logging.getLogger().setLevel(getattr(logging, settings.log_level.upper()))
    logger.info("Starting Skill Interview App in environment=%s", settings.environment)

    try:
        skill_interview_service = SkillInterviewService(settings)
        logger.info("Skill Interview Service initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize Skill Interview Service: %s", e)
        raise


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down Skill Interview App")


@app.get("/healthz", tags=["health"])
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def home(request: Request, record_id: str = "003123456789012345"):
    """Serve the skill interview home page"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "record_id": record_id
    })


@app.post("/api/start")
async def start_interview(record_id: str):
    """Start a skill-based interview"""
    try:
        if not skill_interview_service:
            raise HTTPException(status_code=500, detail="Service not initialized")

        result = await skill_interview_service.start_skill_interview(record_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error starting interview")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/api/generate-questions")
async def generate_questions(interview_id: str):
    """Generate interview questions"""
    try:
        if not skill_interview_service:
            raise HTTPException(status_code=500, detail="Service not initialized")

        result = await skill_interview_service.generate_questions(interview_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error generating questions")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/api/answer")
async def submit_answer(interview_id: str, answer: str):
    """Submit answer to current question"""
    try:
        if not skill_interview_service:
            raise HTTPException(status_code=500, detail="Service not initialized")

        result = await skill_interview_service.submit_answer(interview_id, answer)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error submitting answer")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/status/{interview_id}")
async def get_status(interview_id: str):
    """Get interview status"""
    try:
        if not skill_interview_service:
            raise HTTPException(status_code=500, detail="Service not initialized")

        result = await skill_interview_service.get_interview_status(interview_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error getting status")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)