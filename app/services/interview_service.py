from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Dict, Any

from openai import AsyncOpenAI

from app.core.config import get_settings, Settings
from app.models.schemas import OpportunityDiscussed
from app.services.salesforce_client import SalesforceClient

logger = logging.getLogger(__name__)


class InterviewService:
    """Service for managing AI-powered interviews with candidates."""
    
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
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
        
        # In-memory storage for interview sessions (in production, use Redis/database)
        self._interview_sessions: Dict[str, Dict[str, Any]] = {}

    async def start_interview(self, record_id: str) -> Dict[str, Any]:
        """Start an interview by generating a position and yes/no questions."""
        
        # Get the opportunity record
        record_data = self._salesforce_client.query_opportunity_discussed_by_id(record_id)
        if not record_data:
            raise ValueError(f"Opportunity record {record_id} not found")
        
        # Extract resume text
        resume_text = record_data.get("TR1__Candidate__r", {}).get("Candidate_s_Resume_TXT__c", "")
        if not resume_text:
            raise ValueError("Candidate resume text not found")
        
        # Generate position title and yes/no questions using first agent
        position_title, yes_no_questions = await self._generate_position_and_questions(resume_text)
        
        # Create interview session
        interview_id = str(uuid.uuid4())
        interview_session = {
            "interview_id": interview_id,
            "record_id": record_id,
            "position_title": position_title,
            "yes_no_questions": yes_no_questions,
            "resume_text": resume_text,
            "step": "yes_no_questions",
            "yes_no_answers": None,
            "open_ended_questions": None,
            "open_ended_answers": None,
            "summary": None
        }
        
        self._interview_sessions[interview_id] = interview_session
        
        return {
            "interview_id": interview_id,
            "record_id": record_id,
            "position_title": position_title,
            "yes_no_questions": yes_no_questions,
            "message": "Interview started. Please answer the yes/no questions."
        }

    async def submit_yes_no_answers(self, interview_id: str, answers: List[bool]) -> Dict[str, Any]:
        """Submit yes/no answers and generate open-ended questions."""
        
        if interview_id not in self._interview_sessions:
            raise ValueError("Interview session not found")
        
        session = self._interview_sessions[interview_id]
        if session["step"] != "yes_no_questions":
            raise ValueError("Invalid step. Expected yes/no questions step.")
        
        if len(answers) != len(session["yes_no_questions"]):
            raise ValueError(f"Expected {len(session['yes_no_questions'])} answers, got {len(answers)}")
        
        # Store answers
        session["yes_no_answers"] = answers
        session["step"] = "open_ended_questions"
        
        # Generate open-ended questions using second agent
        open_ended_questions = await self._generate_open_ended_questions(
            session["resume_text"], 
            session["position_title"], 
            session["yes_no_questions"], 
            answers
        )
        
        session["open_ended_questions"] = open_ended_questions
        
        return {
            "interview_id": interview_id,
            "yes_no_answers": {"answers": answers},
            "open_ended_questions": open_ended_questions,
            "message": "Please answer the open-ended questions."
        }

    async def complete_interview(self, interview_id: str, open_ended_answers: List[str]) -> Dict[str, Any]:
        """Complete the interview and save to Salesforce."""
        
        if interview_id not in self._interview_sessions:
            raise ValueError("Interview session not found")
        
        session = self._interview_sessions[interview_id]
        if session["step"] != "open_ended_questions":
            raise ValueError("Invalid step. Expected open-ended questions step.")
        
        if len(open_ended_answers) != len(session["open_ended_questions"]):
            raise ValueError(f"Expected {len(session['open_ended_questions'])} answers, got {len(open_ended_answers)}")
        
        # Store answers
        session["open_ended_answers"] = open_ended_answers
        session["step"] = "completed"
        
        # Generate interview summary
        summary = await self._generate_interview_summary(
            session["resume_text"],
            session["position_title"],
            session["yes_no_questions"],
            session["yes_no_answers"],
            session["open_ended_questions"],
            open_ended_answers
        )
        
        session["summary"] = summary
        
        # Save to Salesforce
        await self._save_interview_to_salesforce(
            session["record_id"],
            summary
        )
        
        return {
            "interview_id": interview_id,
            "record_id": session["record_id"],
            "summary": summary,
            "message": "Interview completed and saved to Salesforce."
        }

    async def _generate_position_and_questions(self, resume_text: str) -> tuple[str, List[str]]:
        """Generate a position title and three yes/no questions based on resume."""
        
        prompt = (
            "You are an AI recruiter analyzing a candidate's resume. "
            "Based on the resume text below, generate:\n\n"
            "1. A realistic job position title that this candidate could apply for\n"
            "2. Three yes/no questions that would help assess their fit for this position\n\n"
            "The questions should be specific and relevant to the position requirements.\n\n"
            f"Resume Text:\n{resume_text}\n\n"
            "Respond in this exact format:\n"
            "POSITION: [Job Title]\n"
            "QUESTION 1: [First yes/no question]\n"
            "QUESTION 2: [Second yes/no question]\n"
            "QUESTION 3: [Third yes/no question]"
        )
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a precise recruiter who generates relevant interview questions."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            
            content = response.choices[0].message.content or ""
            
            # Parse response
            lines = content.strip().split('\n')
            position_title = "Software Developer"  # default
            questions = []
            
            for line in lines:
                if line.startswith("POSITION:"):
                    position_title = line.replace("POSITION:", "").strip()
                elif line.startswith("QUESTION"):
                    question = line.split(":", 1)[1].strip() if ":" in line else line.strip()
                    if question:
                        questions.append(question)
            
            # Ensure we have exactly 3 questions
            if len(questions) < 3:
                questions.extend([
                    "Do you have experience with modern development practices?",
                    "Are you comfortable working in a team environment?",
                    "Can you handle multiple priorities effectively?"
                ])
            elif len(questions) > 3:
                questions = questions[:3]
            
            return position_title, questions
            
        except Exception as e:
            logger.error("Failed to generate position and questions: %s", e)
            # Fallback questions
            fallback_questions = [
                "Do you have relevant experience for this position?",
                "Are you available to start within the next month?",
                "Can you work in the specified location?"
            ]
            return "Software Developer", fallback_questions

    async def _generate_open_ended_questions(self, resume_text: str, position_title: str, 
                                           yes_no_questions: List[str], yes_no_answers: List[bool]) -> List[str]:
        """Generate two open-ended questions based on resume and yes/no answers."""
        
        # Create context from yes/no answers
        answer_context = []
        for i, (question, answer) in enumerate(zip(yes_no_questions, yes_no_answers)):
            answer_text = "Yes" if answer else "No"
            answer_context.append(f"Q{i+1}: {question} - Answer: {answer_text}")
        
        prompt = (
            "You are an AI recruiter conducting a follow-up interview. "
            "Based on the candidate's resume and their answers to initial screening questions, "
            "generate two thoughtful, open-ended questions that will help assess their fit for the position.\n\n"
            f"Position: {position_title}\n\n"
            f"Resume Summary: {resume_text[:500]}...\n\n"
            f"Initial Screening Answers:\n" + "\n".join(answer_context) + "\n\n"
            "Generate two open-ended questions that:\n"
            "1. Are specific to the position and candidate's background\n"
            "2. Require detailed, thoughtful responses\n"
            "3. Help assess technical skills, experience, or cultural fit\n\n"
            "Respond in this exact format:\n"
            "QUESTION 1: [First open-ended question]\n"
            "QUESTION 2: [Second open-ended question]"
        )
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a skilled interviewer who asks insightful follow-up questions."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
            )
            
            content = response.choices[0].message.content or ""
            
            # Parse response
            lines = content.strip().split('\n')
            questions = []
            
            for line in lines:
                if line.startswith("QUESTION"):
                    question = line.split(":", 1)[1].strip() if ":" in line else line.strip()
                    if question:
                        questions.append(question)
            
            # Ensure we have exactly 2 questions
            if len(questions) < 2:
                questions.extend([
                    "Can you describe a challenging project you've worked on and how you overcame obstacles?",
                    "What motivates you in your work and how do you stay current with industry trends?"
                ])
            elif len(questions) > 2:
                questions = questions[:2]
            
            return questions
            
        except Exception as e:
            logger.error("Failed to generate open-ended questions: %s", e)
            # Fallback questions
            fallback_questions = [
                "Can you describe a challenging project you've worked on and how you overcame obstacles?",
                "What motivates you in your work and how do you stay current with industry trends?"
            ]
            return fallback_questions

    async def _generate_interview_summary(self, resume_text: str, position_title: str,
                                        yes_no_questions: List[str], yes_no_answers: List[bool],
                                        open_ended_questions: List[str], open_ended_answers: List[str]) -> str:
        """Generate a comprehensive interview summary."""
        
        # Create context from all questions and answers
        yes_no_context = []
        for i, (question, answer) in enumerate(zip(yes_no_questions, yes_no_answers)):
            answer_text = "Yes" if answer else "No"
            yes_no_context.append(f"Q{i+1}: {question} - Answer: {answer_text}")
        
        open_ended_context = []
        for i, (question, answer) in enumerate(zip(open_ended_questions, open_ended_answers)):
            open_ended_context.append(f"Q{i+1}: {question}\nAnswer: {answer}")
        
        prompt = (
            "You are an AI recruiter summarizing an interview. "
            "Create a comprehensive summary of the candidate's responses and overall assessment.\n\n"
            f"Position: {position_title}\n\n"
            f"Resume Summary: {resume_text[:300]}...\n\n"
            "Yes/No Screening Questions and Answers:\n" + "\n".join(yes_no_context) + "\n\n"
            "Open-Ended Questions and Answers:\n" + "\n".join(open_ended_context) + "\n\n"
            "Provide a professional summary that includes:\n"
            "1. Key insights from their responses\n"
            "2. Assessment of their fit for the position\n"
            "3. Any concerns or strengths identified\n"
            "4. Overall recommendation\n\n"
            "Keep the summary concise but comprehensive (2-3 paragraphs)."
        )
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a professional recruiter who writes clear, objective interview summaries."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            
            content = response.choices[0].message.content or ""
            return content.strip()
            
        except Exception as e:
            logger.error("Failed to generate interview summary: %s", e)
            return "Interview summary could not be generated due to technical issues."

    async def _save_interview_to_salesforce(self, record_id: str, summary: str) -> None:
        """Save the interview record to Salesforce."""
        
        try:
            sf = self._salesforce_client.get_client()
            
            # Check if AI_Interview__c record already exists
            query = f"SELECT Id FROM AI_Interview__c WHERE Opportunity_Discussed__c = '{record_id}'"
            result = sf.query(query)
            
            if result.get("totalSize", 0) > 0:
                # Update existing record
                interview_id = result["records"][0]["Id"]
                sf.AI_Interview__c.update(interview_id, {
                    "Interview_Summary__c": summary
                })
                logger.info("Updated existing AI_Interview__c record %s", interview_id)
            else:
                # Create new record
                new_record = sf.AI_Interview__c.create({
                    "Opportunity_Discussed__c": record_id,
                    "Interview_Summary__c": summary
                })
                logger.info("Created new AI_Interview__c record %s", new_record["id"])
                
        except Exception as e:
            logger.error("Failed to save interview to Salesforce: %s", e)
            raise RuntimeError(f"Failed to save interview to Salesforce: {e}")

    def get_interview_session(self, interview_id: str) -> Optional[Dict[str, Any]]:
        """Get interview session data."""
        return self._interview_sessions.get(interview_id)

    def cleanup_interview_session(self, interview_id: str) -> None:
        """Clean up interview session data."""
        if interview_id in self._interview_sessions:
            del self._interview_sessions[interview_id]
