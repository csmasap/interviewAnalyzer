import os
import sys
import asyncio
import pytest


BACKEND_PATH = os.path.join(os.path.dirname(__file__), "..", "external", "THEIA-Job-Seekers", "backend")
BACKEND_PATH = os.path.abspath(BACKEND_PATH)
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)


def _vertex_env_ready() -> bool:
    project = (os.getenv("GOOGLE_CLOUD_PROJECT_ID") or os.getenv("PROJECT_ID") or "").strip()
    creds = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    return bool(project and creds and os.path.exists(creds))


@pytest.mark.skipif(not os.getenv("RUN_AI_TESTS"), reason="Set RUN_AI_TESTS=1 to enable real model tests")
@pytest.mark.skipif(not _vertex_env_ready(), reason="Vertex env not configured (GOOGLE_CLOUD_PROJECT_ID or ADC missing)")
def test_isa_chat_vertex_roundtrip_ack_and_next_question():
    # Import inside test so env checks happen first
    from theia_agents.isa_chat import ISAChat
    from models import (
        InterviewSession,
        InterviewMode,
    )

    async def run_flow():
        chat = ISAChat()
        assert chat.model is not None, "Vertex model failed to initialize"

        job_description = (
            "You will onboard new B2B customers, drive early value, and coordinate cross-functional implementation. "
            "Required: project management, stakeholder communication, problem solving, and product proficiency."
        )

        # 1) Generate questions with the real model
        qout = await chat.generate_questions_from_job_description(
            job_description=job_description,
            job_title="Customer Success Manager",
            company_name="Ramp",
        )
        assert qout and len(qout.questions) == 10

        # 2) Build session and submit an answer; conduct_interview should advance index
        session = InterviewSession(
            session_id="ai_integration_session",
            user_id="demo_user",
            interview_mode=InterviewMode.TEXT,
            job_description=job_description,
            company_name="Ramp",
            job_title="Customer Success Manager",
        )

        updated = await chat.conduct_interview(
            session=session,
            questions_output=qout,
            user_answer="I enjoy helping customers realize value quickly and I use STAR examples.",
            client_id=None,  # local run without websocket
        )
        assert updated.current_question_index == 1

        # 3) Ask the model for acknowledgement/feedback explicitly and print it
        validation = await chat.validate_answer(
            "I enjoy helping customers realize value quickly and I use STAR examples.",
            qout.questions[0],
            job_title="Customer Success Manager",
            company_name="Ramp",
        )
        feedback = await chat.provide_feedback(validation, job_title="Customer Success Manager", company_name="Ramp")
        print("=== MODEL FEEDBACK START ===")
        print(feedback)
        print("=== MODEL FEEDBACK END ===")
        assert isinstance(feedback, str) and len(feedback.strip()) > 0

    asyncio.run(run_flow())


