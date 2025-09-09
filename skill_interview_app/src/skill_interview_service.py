from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Dict, Any

from openai import AsyncOpenAI

from .config import Settings
from .salesforce_client import SalesforceClient

logger = logging.getLogger(__name__)


class SkillInterviewService:
    """Service for conducting skill-based interviews with sequential questions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Please set it in the environment.")

        self._client = AsyncOpenAI(
            api_key=self._settings.openai_api_key,
            base_url=self._settings.openai_base_url or None,
            timeout=float(self._settings.openai_timeout_seconds),
            max_retries=int(self._settings.openai_max_retries),
        )
        self._model = self._settings.openai_model
        self._salesforce_client = SalesforceClient(settings)

        # In-memory storage for interview sessions
        self._interview_sessions: Dict[str, Dict[str, Any]] = {}

    async def start_skill_interview(self, record_id: str) -> Dict[str, Any]:
        """Start a skill-based interview by extracting skills from resume."""

        logger.info(f"Starting skill interview for record_id: {record_id}")

        # Get resume text from Salesforce Contact record
        resume_text = self._get_resume_text_from_contact(record_id)
        if not resume_text:
            raise ValueError(f"No resume text found for Contact record {record_id}")

        # Extract 7 most relevant skills
        skills = await self._extract_skills_from_resume(resume_text)

        # Create interview session
        interview_id = str(uuid.uuid4())
        interview_session = {
            "interview_id": interview_id,
            "record_id": record_id,
            "resume_text": resume_text,
            "skills": skills,
            "questions": [],
            "answers": [],
            "current_question_index": 0,
            "step": "generating_questions",
            "transcript": []
        }

        self._interview_sessions[interview_id] = interview_session

        return {
            "interview_id": interview_id,
            "record_id": record_id,
            "skills": skills,
            "message": "Skills extracted successfully. Generating interview questions..."
        }

    async def generate_questions(self, interview_id: str) -> Dict[str, Any]:
        """Generate 7 questions based on extracted skills."""

        if interview_id not in self._interview_sessions:
            raise ValueError("Interview session not found")

        session = self._interview_sessions[interview_id]
        if session["step"] != "generating_questions":
            raise ValueError("Invalid step. Expected generating_questions step.")

        # Generate questions based on skills
        questions = await self._generate_questions_from_skills(session["skills"], session["resume_text"])

        session["questions"] = questions
        session["step"] = "interviewing"
        session["transcript"].append({
            "type": "system",
            "content": f"Interview started with {len(questions)} questions based on skills: {', '.join(session['skills'])}"
        })

        return {
            "interview_id": interview_id,
            "questions": questions,
            "current_question": questions[0] if questions else None,
            "message": "Questions generated. Ready to start interview."
        }

    async def submit_answer(self, interview_id: str, answer: str) -> Dict[str, Any]:
        """Submit answer to current question and get next question."""

        if interview_id not in self._interview_sessions:
            raise ValueError("Interview session not found")

        session = self._interview_sessions[interview_id]
        if session["step"] != "interviewing":
            raise ValueError("Invalid step. Expected interviewing step.")

        current_index = session["current_question_index"]

        # Store the answer
        session["answers"].append(answer)
        session["transcript"].append({
            "type": "question",
            "content": session["questions"][current_index],
            "question_number": current_index + 1
        })
        session["transcript"].append({
            "type": "answer",
            "content": answer,
            "question_number": current_index + 1
        })

        # Move to next question
        session["current_question_index"] = current_index + 1

        # Check if interview is complete
        if session["current_question_index"] >= len(session["questions"]):
            session["step"] = "completed"
            transcript = await self._generate_transcript(session)
            session["final_transcript"] = transcript

            return {
                "interview_id": interview_id,
                "completed": True,
                "transcript": transcript,
                "message": "Interview completed successfully."
            }
        else:
            next_question = session["questions"][session["current_question_index"]]
            return {
                "interview_id": interview_id,
                "completed": False,
                "next_question": next_question,
                "question_number": session["current_question_index"] + 1,
                "total_questions": len(session["questions"]),
                "message": f"Question {session['current_question_index']} of {len(session['questions'])}"
            }

    async def get_interview_status(self, interview_id: str) -> Dict[str, Any]:
        """Get current interview status."""

        if interview_id not in self._interview_sessions:
            raise ValueError("Interview session not found")

        session = self._interview_sessions[interview_id]

        return {
            "interview_id": interview_id,
            "step": session["step"],
            "current_question_index": session["current_question_index"],
            "total_questions": len(session["questions"]),
            "skills": session["skills"],
            "completed": session["step"] == "completed"
        }

    def _get_resume_text_from_contact(self, contact_id: str) -> Optional[str]:
        """Extract resume text from Salesforce Contact record."""

        try:
            contact_data = self._salesforce_client.query_contact_by_id(contact_id)
            if contact_data:
                return contact_data.get("Candidate_s_Resume_TXT__c", "")
        except Exception as e:
            logger.error(f"Failed to query Contact record {contact_id}: {str(e)}")

        return None

    async def _extract_skills_from_resume(self, resume_text: str) -> List[str]:
        """Extract 7 most relevant skills from resume text."""

        prompt = (
            "You are an expert HR professional analyzing a candidate's resume. "
            "Based on the resume text provided, identify the 7 most relevant technical and professional skills "
            "that this candidate possesses. Consider their experience level and focus on skills that would be "
            "valuable in a professional setting.\n\n"
            "If the candidate has less than 5 years of experience, prioritize skills from their education, "
            "projects, certifications, and any professional experience they have.\n\n"
            "Return exactly 7 skills, one per line, focusing on:\n"
            "- Technical skills (programming languages, frameworks, tools)\n"
            "- Professional skills (communication, leadership, problem-solving)\n"
            "- Domain-specific knowledge\n\n"
            f"Resume Text:\n{resume_text}\n\n"
            "Skills (one per line):"
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a skilled recruiter who identifies key candidate skills."},
                    {"role": "user", "content": prompt},
                ],
            )

            content = response.choices[0].message.content or ""
            skills = [line.strip() for line in content.split('\n') if line.strip()]

            # Ensure we have exactly 7 skills
            if len(skills) < 7:
                # Add generic skills if needed
                default_skills = [
                    "Problem Solving", "Communication", "Team Collaboration",
                    "Time Management", "Adaptability", "Critical Thinking", "Project Management"
                ]
                skills.extend(default_skills[len(skills):7])
            elif len(skills) > 7:
                skills = skills[:7]

            return skills

        except Exception as e:
            logger.error(f"Failed to extract skills: {str(e)}")
            return [
                "Problem Solving", "Communication", "Team Collaboration",
                "Time Management", "Adaptability", "Critical Thinking", "Project Management"
            ]

    async def _generate_questions_from_skills(self, skills: List[str], resume_text: str) -> List[str]:
        """Generate 7 interview questions based on extracted skills."""

        skills_text = "\n".join(f"- {skill}" for skill in skills)

        prompt = (
            "You are an experienced interviewer creating targeted questions based on a candidate's skills. "
            "Based on the following skills extracted from the candidate's resume, create 7 thoughtful, "
            "open-ended interview questions that assess these skills in a professional context.\n\n"
            f"Skills:\n{skills_text}\n\n"
            f"Resume Context: {resume_text[:500]}...\n\n"
            "Create questions that:\n"
            "- Are open-ended and require detailed responses\n"
            "- Test practical application of the skills\n"
            "- Encourage the candidate to provide specific examples\n"
            "- Assess both technical proficiency and soft skills\n"
            "- Are appropriate for the candidate's experience level\n\n"
            "Return exactly 7 questions, one per line:"
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a professional interviewer who creates insightful questions."},
                    {"role": "user", "content": prompt},
                ],
            )

            content = response.choices[0].message.content or ""
            questions = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith("Question")]

            # Clean up questions (remove numbering if present)
            cleaned_questions = []
            for q in questions:
                # Remove leading numbers like "1.", "2.", etc.
                q = q.strip()
                if q and any(q.startswith(f"{i}.") or q.startswith(f"{i})") for i in range(1, 10)):
                    q = q.split('.', 1)[1].strip() if '.' in q else q.split(')', 1)[1].strip()
                if q:
                    cleaned_questions.append(q)

            # Ensure we have exactly 7 questions
            if len(cleaned_questions) < 7:
                default_questions = [
                    "Can you describe a challenging problem you've solved using your technical skills?",
                    "How do you approach learning new technologies or skills?",
                    "Tell me about a time when you had to collaborate with others to achieve a goal.",
                    "How do you handle tight deadlines or changing priorities?",
                    "What motivates you in your work?",
                    "How do you ensure the quality of your work?",
                    "Where do you see yourself developing professionally in the next few years?"
                ]
                cleaned_questions.extend(default_questions[len(cleaned_questions):7])
            elif len(cleaned_questions) > 7:
                cleaned_questions = cleaned_questions[:7]

            return cleaned_questions

        except Exception as e:
            logger.error(f"Failed to generate questions: {str(e)}")
            return [
                "Can you describe a challenging problem you've solved using your technical skills?",
                "How do you approach learning new technologies or skills?",
                "Tell me about a time when you had to collaborate with others to achieve a goal.",
                "How do you handle tight deadlines or changing priorities?",
                "What motivates you in your work?",
                "How do you ensure the quality of your work?",
                "Where do you see yourself developing professionally in the next few years?"
            ]

    async def _generate_transcript(self, session: Dict[str, Any]) -> str:
        """Generate a comprehensive interview transcript."""

        transcript_lines = []
        transcript_lines.append("SKILL-BASED INTERVIEW TRANSCRIPT")
        transcript_lines.append("=" * 50)
        transcript_lines.append(f"Candidate ID: {session['record_id']}")
        transcript_lines.append(f"Interview Date: {uuid.uuid4().hex[:8]}")  # Simple timestamp
        transcript_lines.append("")

        transcript_lines.append("EXTRACTED SKILLS:")
        for i, skill in enumerate(session["skills"], 1):
            transcript_lines.append(f"{i}. {skill}")
        transcript_lines.append("")

        transcript_lines.append("INTERVIEW QUESTIONS AND ANSWERS:")
        transcript_lines.append("-" * 40)

        for i, (question, answer) in enumerate(zip(session["questions"], session["answers"]), 1):
            transcript_lines.append(f"Question {i}: {question}")
            transcript_lines.append(f"Answer {i}: {answer}")
            transcript_lines.append("")

        transcript_lines.append("END OF INTERVIEW")
        transcript_lines.append("=" * 50)

        return "\n".join(transcript_lines)

    def get_interview_session(self, interview_id: str) -> Optional[Dict[str, Any]]:
        """Get interview session data."""
        return self._interview_sessions.get(interview_id)

    def cleanup_interview_session(self, interview_id: str) -> None:
        """Clean up interview session data."""
        if interview_id in self._interview_sessions:
            del self._interview_sessions[interview_id]