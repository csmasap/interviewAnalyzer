from __future__ import annotations

import logging
from typing import List, Optional

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class JobAnalyzerService:
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

    async def generate_interview_questions(self, job_description: str) -> List[str]:
        """Generate 3 open-ended interview questions based on the job description."""
        
        prompt = (
            "You are an expert HR professional and interview specialist. Based on the job description provided, "
            "generate exactly 3 thoughtful, open-ended interview questions that would help assess candidates for this role.\n\n"
            "The questions should:\n"
            "- Be open-ended (not yes/no questions)\n"
            "- Test both technical skills and soft skills relevant to the role\n"
            "- Be specific to the requirements mentioned in the job description\n"
            "- Encourage detailed responses that reveal candidate experience and thinking\n"
            "- Be professional and appropriate for an interview setting\n\n"
            f"Job Description:\n{job_description}\n\n"
            "Please provide exactly 3 questions, one per line, numbered 1, 2, 3:"
        )
        
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are an expert interviewer who creates insightful, role-specific interview questions."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,  # Slightly higher for creativity in question generation
            )
            
            content = resp.choices[0].message.content or ""
            
            # Parse the numbered questions
            questions = self._parse_questions(content)
            
            # Ensure we have exactly 3 questions
            if len(questions) < 3:
                logger.warning("Generated fewer than 3 questions, padding with generic ones")
                questions.extend(self._get_fallback_questions()[len(questions):3])
            elif len(questions) > 3:
                questions = questions[:3]
            
            return questions
            
        except Exception as e:
            logger.exception("Failed to generate interview questions: %s", e)
            return self._get_fallback_questions()
    
    def _parse_questions(self, content: str) -> List[str]:
        """Parse numbered questions from the AI response."""
        questions = []
        lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for numbered questions (1., 2., 3. or 1:, 2:, 3:)
            if line and any(line.startswith(f"{i}.") or line.startswith(f"{i}:") for i in range(1, 10)):
                # Remove the number and clean up
                question = line
                for i in range(1, 10):
                    if question.startswith(f"{i}."):
                        question = question[2:].strip()
                        break
                    elif question.startswith(f"{i}:"):
                        question = question[2:].strip()
                        break
                
                if question and len(question) > 10:  # Basic quality check
                    questions.append(question)
        
        return questions
    
    def _get_fallback_questions(self) -> List[str]:
        """Fallback questions in case AI generation fails."""
        return [
            "Can you walk me through a challenging project you've worked on and how you approached solving the key technical problems?",
            "How do you stay current with industry trends and technologies, and can you give me an example of how you've applied something new you learned?",
            "Describe a time when you had to collaborate with team members who had different perspectives or working styles. How did you handle it?"
        ]
