import os
import sys
import asyncio


# Ensure external backend is importable
BACKEND_PATH = os.path.join(os.path.dirname(__file__), "..", "external", "THEIA-Job-Seekers", "backend")
BACKEND_PATH = os.path.abspath(BACKEND_PATH)
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)


def test_isa_chat_advances_index_and_records_answers():
    from theia_agents.isa_chat import ISAChat
    from models import (
        InterviewSession,
        InterviewMode,
        QuestionGenerationOutput,
    )

    async def run_flow():
        # Prepare session and questions
        session = InterviewSession(
            session_id="test_session",
            user_id="test_user",
            interview_mode=InterviewMode.TEXT,
            job_description="Test JD",
            company_name="Ramp",
            job_title="Customer Success Manager",
        )
        questions = [f"Question {i+1}" for i in range(10)]
        qout = QuestionGenerationOutput(
            questions=questions,
            question_rationale=[""] * 10,
            difficulty_levels=["Medium"] * 10,
            skill_coverage={},
            question_types=["General"] * 10,
        )

        chat = ISAChat()
        # Force heuristic path (no Vertex calls)
        chat.model = None

        # First answer should advance index from 0 → 1 and record answer
        updated = await chat.conduct_interview(
            session=session,
            questions_output=qout,
            user_answer="My first answer",
            client_id=None,
        )
        assert updated.current_question_index == 1
        assert updated.answers and updated.answers[-1] == "My first answer"
        assert updated.interview_transcript and updated.interview_transcript[-1]["message"] == "My first answer"

        # Another answer advances to 2
        updated = await chat.conduct_interview(
            session=updated,
            questions_output=qout,
            user_answer="Second answer",
            client_id=None,
        )
        assert updated.current_question_index == 2

    asyncio.run(run_flow())


def test_isa_chat_completes_on_last_question():
    from theia_agents.isa_chat import ISAChat
    from models import (
        InterviewSession,
        InterviewMode,
        InterviewStatus,
        InterviewPhase,
        QuestionGenerationOutput,
    )

    async def run_flow():
        session = InterviewSession(
            session_id="test_session2",
            user_id="test_user",
            interview_mode=InterviewMode.TEXT,
            job_description="Test JD",
            company_name="Ramp",
            job_title="Customer Success Manager",
        )
        # Start at last question
        session.current_question_index = 9
        questions = [f"Question {i+1}" for i in range(10)]
        qout = QuestionGenerationOutput(
            questions=questions,
            question_rationale=[""] * 10,
            difficulty_levels=["Medium"] * 10,
            skill_coverage={},
            question_types=["General"] * 10,
        )

        chat = ISAChat()
        chat.model = None

        updated = await chat.conduct_interview(
            session=session,
            questions_output=qout,
            user_answer="Final answer",
            client_id=None,
        )

        assert updated.status == InterviewStatus.COMPLETED
        assert updated.phase == InterviewPhase.EVALUATION
        assert updated.completed_at is not None

    asyncio.run(run_flow())


