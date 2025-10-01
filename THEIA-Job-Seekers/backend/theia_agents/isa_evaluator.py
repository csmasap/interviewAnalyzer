"""
ISA_Evaluator Agent - Interview Assessment and Feedback
Google Vertex AI agent for evaluating interview performance and providing comprehensive feedback.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel
import json

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import EvaluationOutput, SkillsDetectionOutput, QuestionGenerationOutput
from config import settings
from .base_agent import OptimizedAgent, TaskComplexity

logger = logging.getLogger(__name__)


class ISAEvaluator(OptimizedAgent):
    """
    ISA_Evaluator Agent
    
    Provides comprehensive interview evaluation including:
    - Job matching feedback based on detected skills
    - Interviewing skills assessment (communication, confidence, etc.)
    - Individual skill assessments against requirements
    - Strengths and improvement areas identification
    - Specific recommendations for interview preparation
    - Overall interview readiness scoring
    """
    
    def __init__(self):
        """Initialize the ISA_Evaluator agent with optimizations"""
        super().__init__("ISA_Evaluator")
    
    async def evaluate_interview_performance(
        self,
        questions: List[str],
        answers: List[str],
        job_title: str,
        company_name: str,
        job_description: str,
        candidate_resume: str,
        skills_output: Optional[SkillsDetectionOutput] = None,
        questions_output: Optional[QuestionGenerationOutput] = None,
        interview_transcript: Optional[List[Dict[str, Any]]] = None
    ) -> EvaluationOutput:
        """
        Evaluate complete interview performance
        
        Args:
            questions: List of interview questions asked
            answers: List of candidate's answers
            job_title: Job title/position
            company_name: Company name
            skills_output: Skills analysis from ISA_Detector
            questions_output: Questions metadata from ISA_Questioner
            interview_transcript: Full interview transcript
            
        Returns:
            EvaluationOutput: Comprehensive evaluation and feedback
        """
        logger.info(f"🔍 Evaluating interview performance for {job_title} at {company_name}")
        
        try:
            # Create evaluation prompt with all inputs
            evaluation_prompt = self._create_evaluation_prompt(
                questions, answers, job_title, company_name, job_description, candidate_resume,
                skills_output, questions_output, interview_transcript
            )
            
            # Generate evaluation using Vertex AI
            evaluation_response = await self._generate_evaluation(evaluation_prompt)
            
            # Parse and structure the evaluation output
            evaluation_output = self._parse_evaluation_response(evaluation_response, job_title)
            
            logger.info(f"✅ Interview evaluation completed for {job_title}")
            return evaluation_output
            
        except Exception as e:
            logger.error(f"❌ Interview evaluation failed for {job_title}: {e}")
            # Return fallback evaluation
            return self._create_fallback_evaluation(job_title, questions, answers)
    
    def _create_evaluation_prompt(
        self,
        questions: List[str],
        answers: List[str],
        job_title: str,
        company_name: str,
        job_description: str,
        candidate_resume: str,
        skills_output: Optional[SkillsDetectionOutput] = None,
        questions_output: Optional[QuestionGenerationOutput] = None,
        interview_transcript: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Create a comprehensive evaluation prompt for the AI model"""
        
        # Build skills context
        skills_context = ""
        if skills_output:
            skills_context = f"""
JOB REQUIREMENTS ANALYSIS:
Key Skills Required: {', '.join(skills_output.key_skills)}
Technical Requirements: {', '.join(skills_output.technical_requirements)}
Soft Skills Focus: {', '.join(skills_output.soft_skills)}
Experience Level: {skills_output.experience_level}
Evaluation Criteria: {skills_output.scorecard_criteria}
"""
        
        # Build questions context
        questions_context = ""
        if questions_output:
            skill_coverage = questions_output.skill_coverage
            question_types = questions_output.question_types
            questions_context = f"""
QUESTION DESIGN ANALYSIS:
Skill Coverage Map: {skill_coverage}
Question Types: {', '.join(set(question_types))}
Difficulty Distribution: {', '.join(questions_output.difficulty_levels)}
"""
        
        # Format Q&A pairs
        qa_pairs = []
        for i, (q, a) in enumerate(zip(questions, answers), 1):
            qa_pairs.append(f"""
Q{i}: {q}
A{i}: {a}
""")
        
        qa_section = "\n".join(qa_pairs)
        
        # Add job description and resume context
        job_context = f"""
JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{candidate_resume[:2000] if candidate_resume else "No resume available"}
{'...(truncated)' if len(candidate_resume) > 2000 else ''}
"""

        prompt = f"""
You are ISA_Evaluator, an expert interview assessment specialist and career development advisor.

EVALUATION TASK:
Provide comprehensive evaluation of this interview performance, including job matching assessment and interviewing skills analysis.

INTERVIEW DETAILS:
Position: {job_title}
Company: {company_name}
Number of Questions: {len(questions)}
Number of Answers: {len(answers)}

{job_context}

{skills_context}

{questions_context}

INTERVIEW Q&A ANALYSIS (PRIMARY SOURCE - 95% WEIGHT):
{qa_section}

CRITICAL EVALUATION GUIDELINES:
- WEIGHT INTERVIEW RESPONSES 95% and RESUME 5% in your assessment
- The interview transcript is the PRIMARY source of truth about candidate capabilities
- Use resume only for context and background verification
- Focus on what the candidate DEMONSTRATED in their answers, not what's written on resume
- Assess based on ISA_Detector scorecard criteria for this specific job
- Be specific about evidence from actual interview responses

EVALUATION FRAMEWORK:
Assess the candidate on two primary dimensions:

1. JOB MATCHING FEEDBACK (Based on ISA_Detector Scorecard):
   - How well do their INTERVIEW RESPONSES demonstrate job requirements?
   - Evidence of required competencies shown in answers (95% weight)
   - Resume background context (5% weight only)
   - Specific examples given during interview
   - Alignment with detected skills from job analysis

2. INTERVIEWING SKILLS ASSESSMENT:
   - Clear & Concise Communication (1-10)
   - Confidence & Professionalism (1-10) 
   - Active Listening (1-10)
   - Thoughtful and Relevant Responses (1-10)
   - Adaptability and Problem-Solving Ability (1-10)

OUTPUT REQUIREMENTS:
Provide detailed evaluation in JSON format with these exact fields:

{
    "job_matching_score": 7.5,
    "interviewing_skills": {
        "clear_concise_communication": 8.0,
        "confidence_professionalism": 7.5,
        "active_listening": 8.5,
        "thoughtful_relevant_responses": 7.0,
        "adaptability_problem_solving": 8.0
    },
    "skill_assessments": {
        "Key Skill 1": 8.0,
        "Key Skill 2": 6.5,
        "Key Skill 3": 7.5,
        "Technical Skills": 7.0,
        "Communication": 8.5,
        "Problem Solving": 7.5
    },
    "strengths": [
        "Strong communication skills demonstrated throughout",
        "Good technical knowledge in relevant areas",
        "Showed adaptability in problem-solving scenarios",
        "Professional demeanor and confidence"
    ],
    "improvement_areas": [
        "Could provide more specific examples in behavioral questions",
        "Technical depth could be stronger in certain areas",
        "More preparation on company-specific questions needed"
    ],
    "overall_feedback": "Comprehensive 3-4 sentence summary of overall performance, highlighting key strengths and main areas for development. Include specific examples from their responses.",
    "recommendations": [
        "Practice STAR method for behavioral questions",
        "Research company culture and values more thoroughly",
        "Prepare specific examples demonstrating technical skills",
        "Work on providing more quantifiable achievements"
    ],
    "interview_readiness": 7.8
}

SCORING GUIDELINES:
- Use 1-10 scale where 1=Poor, 5=Average, 10=Excellent
- Job matching score reflects alignment with role requirements
- Interviewing skills scores assess interview performance quality
- Skill assessments evaluate demonstration of specific competencies
- Interview readiness is overall assessment of preparation level

EVALUATION CRITERIA:

JOB MATCHING (1-10):
- 1-3: Poor fit, major skill gaps evident
- 4-6: Some alignment but significant development needed
- 7-8: Good fit with minor gaps or development areas
- 9-10: Excellent fit, strong demonstration of all requirements

INTERVIEWING SKILLS (1-10 each):
- Clear & Concise Communication: Articulation, structure, clarity
- Confidence & Professionalism: Poise, self-assurance, appropriate demeanor
- Active Listening: Understanding questions, asking clarifications, engagement
- Thoughtful & Relevant Responses: Quality, relevance, depth of answers
- Adaptability & Problem-Solving: Handling unexpected questions, creative thinking

CRITICAL GUIDELINES:
- Be constructive and encouraging while honest about areas for improvement
- Provide specific examples from their responses to support assessments
- Focus on actionable feedback and development recommendations
- Consider the experience level and adjust expectations accordingly
- Highlight both technical and soft skill demonstrations
- Include specific preparation recommendations for future interviews

Generate comprehensive interview evaluation now:
"""
        return prompt
    
    async def _generate_evaluation(self, prompt: str) -> str:
        """Generate evaluation using optimized Vertex AI model"""
        # Evaluation requires complex analysis - use pro model with moderate timeout
        return await self.generate_optimized(
            prompt=prompt,
            complexity=TaskComplexity.COMPLEX,  # Use pro model for detailed evaluation
            max_tokens=2500,  # Reduced from 3000 for faster response
            timeout=45,  # Reduced from 90s to 45s
            use_cache=False  # Don't cache evaluations - each should be unique
        )
    
    def _parse_evaluation_response(self, response: str, job_title: str) -> EvaluationOutput:
        """Parse the AI response into structured EvaluationOutput"""
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response[json_start:json_end]
            eval_data = json.loads(json_str)
            
            # Validate and normalize scores (ensure 0-10 range)
            job_matching_score = max(0.0, min(10.0, eval_data.get("job_matching_score", 5.0)))
            interview_readiness = max(0.0, min(10.0, eval_data.get("interview_readiness", 5.0)))
            
            # Validate interviewing skills scores
            interviewing_skills = eval_data.get("interviewing_skills", {})
            for skill, score in interviewing_skills.items():
                interviewing_skills[skill] = max(0.0, min(10.0, score))
            
            # Validate skill assessments
            skill_assessments = eval_data.get("skill_assessments", {})
            for skill, score in skill_assessments.items():
                skill_assessments[skill] = max(0.0, min(10.0, score))
            
            # Create EvaluationOutput from parsed data
            return EvaluationOutput(
                job_matching_score=job_matching_score,
                interviewing_skills=interviewing_skills,
                skill_assessments=skill_assessments,
                strengths=eval_data.get("strengths", []),
                improvement_areas=eval_data.get("improvement_areas", []),
                overall_feedback=eval_data.get("overall_feedback", f"Evaluation completed for {job_title} position."),
                recommendations=eval_data.get("recommendations", []),
                interview_readiness=interview_readiness
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to parse evaluation response: {e}")
            # Return fallback evaluation
            return self._create_fallback_evaluation(job_title, [], [])
    
    def _create_fallback_evaluation(
        self,
        job_title: str,
        questions: List[str],
        answers: List[str]
    ) -> EvaluationOutput:
        """Create fallback evaluation when primary evaluation fails"""
        
        # Calculate basic metrics from answers
        avg_answer_length = sum(len(answer.split()) for answer in answers) / len(answers) if answers else 0
        
        # Basic scoring based on answer quality indicators
        base_score = 5.0  # Start with average
        
        if avg_answer_length > 50:  # Detailed answers
            base_score += 1.0
        elif avg_answer_length < 20:  # Very short answers
            base_score -= 1.0
        
        # Ensure score is in valid range
        base_score = max(1.0, min(10.0, base_score))
        
        return EvaluationOutput(
            job_matching_score=base_score,
            interviewing_skills={
                "clear_concise_communication": base_score,
                "confidence_professionalism": base_score,
                "active_listening": base_score,
                "thoughtful_relevant_responses": base_score,
                "adaptability_problem_solving": base_score
            },
            skill_assessments={
                "Professional Communication": base_score,
                "Problem Solving": base_score,
                "Technical Knowledge": base_score,
                "Cultural Fit": base_score
            },
            strengths=[
                "Participated in the complete interview process",
                "Provided responses to all questions asked",
                "Demonstrated engagement with the interview",
                "Showed willingness to discuss experience"
            ],
            improvement_areas=[
                "Could provide more detailed examples in responses",
                "Practice articulating technical concepts clearly",
                "Prepare more specific examples from past experience",
                "Research company and role more thoroughly"
            ],
            overall_feedback=f"The candidate completed the interview for the {job_title} position and provided responses to all questions. This evaluation represents a baseline assessment due to limited data processing. A more detailed evaluation would require additional context and analysis.",
            recommendations=[
                "Practice common interview questions and responses",
                "Prepare specific examples using the STAR method",
                "Research the company and role thoroughly",
                "Practice articulating technical concepts clearly",
                "Prepare questions to ask the interviewer"
            ],
            interview_readiness=base_score
        )
    
    async def generate_detailed_feedback_report(
        self,
        evaluation_output: EvaluationOutput,
        candidate_name: str,
        job_title: str,
        company_name: str
    ) -> Dict[str, Any]:
        """Generate a detailed feedback report for the candidate"""
        
        report = {
            "candidate_name": candidate_name,
            "position": job_title,
            "company": company_name,
            "evaluation_date": datetime.utcnow().isoformat(),
            "overall_assessment": {
                "job_matching_score": evaluation_output.job_matching_score,
                "interview_readiness": evaluation_output.interview_readiness,
                "performance_level": self._get_performance_level(evaluation_output.interview_readiness)
            },
            "detailed_scores": {
                "interviewing_skills": evaluation_output.interviewing_skills,
                "skill_assessments": evaluation_output.skill_assessments
            },
            "feedback_summary": {
                "strengths": evaluation_output.strengths,
                "improvement_areas": evaluation_output.improvement_areas,
                "overall_feedback": evaluation_output.overall_feedback
            },
            "development_plan": {
                "immediate_actions": evaluation_output.recommendations[:3],
                "long_term_development": evaluation_output.recommendations[3:],
                "practice_areas": self._identify_practice_areas(evaluation_output),
                "resources": self._suggest_resources(evaluation_output)
            },
            "next_steps": self._generate_next_steps(evaluation_output)
        }
        
        return report
    
    def _get_performance_level(self, score: float) -> str:
        """Determine performance level based on score"""
        if score >= 8.5:
            return "Excellent - Interview Ready"
        elif score >= 7.0:
            return "Good - Minor Preparation Needed"
        elif score >= 5.5:
            return "Average - Moderate Preparation Required"
        elif score >= 4.0:
            return "Below Average - Significant Preparation Needed"
        else:
            return "Needs Development - Extensive Preparation Required"
    
    def _identify_practice_areas(self, evaluation: EvaluationOutput) -> List[str]:
        """Identify specific areas that need practice based on scores"""
        practice_areas = []
        
        # Check interviewing skills
        for skill, score in evaluation.interviewing_skills.items():
            if score < 7.0:
                practice_areas.append(f"Improve {skill.replace('_', ' ').title()}")
        
        # Check skill assessments
        for skill, score in evaluation.skill_assessments.items():
            if score < 6.5:
                practice_areas.append(f"Strengthen {skill}")
        
        return practice_areas[:5]  # Limit to top 5 practice areas
    
    def _suggest_resources(self, evaluation: EvaluationOutput) -> List[Dict[str, str]]:
        """Suggest resources based on evaluation results"""
        resources = []
        
        # Communication improvement
        if evaluation.interviewing_skills.get("clear_concise_communication", 10) < 7.0:
            resources.append({
                "area": "Communication Skills",
                "resource": "Toastmasters International or public speaking courses",
                "description": "Improve verbal communication and presentation skills"
            })
        
        # Technical skills
        avg_technical = sum(
            score for skill, score in evaluation.skill_assessments.items()
            if "technical" in skill.lower()
        ) / max(1, len([s for s in evaluation.skill_assessments if "technical" in s.lower()]))
        
        if avg_technical < 7.0:
            resources.append({
                "area": "Technical Skills",
                "resource": "Online courses (Coursera, Udemy, LinkedIn Learning)",
                "description": "Strengthen technical competencies relevant to the role"
            })
        
        # Interview preparation
        if evaluation.interview_readiness < 7.5:
            resources.append({
                "area": "Interview Preparation",
                "resource": "Mock interview platforms and STAR method training",
                "description": "Practice interview techniques and storytelling methods"
            })
        
        return resources
    
    def _generate_next_steps(self, evaluation: EvaluationOutput) -> List[str]:
        """Generate specific next steps based on evaluation"""
        next_steps = []
        
        if evaluation.interview_readiness >= 8.0:
            next_steps.extend([
                "You're well-prepared for interviews - start applying confidently",
                "Continue practicing to maintain your interview skills",
                "Focus on company-specific research for each application"
            ])
        elif evaluation.interview_readiness >= 6.5:
            next_steps.extend([
                "Address the improvement areas identified in this evaluation",
                "Practice mock interviews focusing on your weaker areas",
                "Prepare 3-5 strong STAR method examples for behavioral questions"
            ])
        else:
            next_steps.extend([
                "Dedicate 2-3 weeks to intensive interview preparation",
                "Work with a career coach or mentor for personalized guidance",
                "Practice basic interview skills before attempting real interviews"
            ])
        
        # Add specific recommendations from evaluation
        next_steps.extend(evaluation.recommendations[:2])
        
        return next_steps[:5]  # Limit to 5 next steps
    
    async def validate_evaluation_quality(self, evaluation_output: EvaluationOutput) -> Dict[str, Any]:
        """Validate the quality and completeness of evaluation output"""
        
        validation_results = {
            "is_valid": True,
            "completeness_score": 0.0,
            "quality_issues": [],
            "recommendations": []
        }
        
        # Check score validity
        score_fields = [
            ("job_matching_score", evaluation_output.job_matching_score),
            ("interview_readiness", evaluation_output.interview_readiness)
        ]
        
        for field_name, score in score_fields:
            if not (0.0 <= score <= 10.0):
                validation_results["quality_issues"].append(f"Invalid {field_name}: {score}")
                validation_results["is_valid"] = False
        
        # Check interviewing skills scores
        required_interviewing_skills = [
            "clear_concise_communication",
            "confidence_professionalism", 
            "active_listening",
            "thoughtful_relevant_responses",
            "adaptability_problem_solving"
        ]
        
        missing_skills = [
            skill for skill in required_interviewing_skills
            if skill not in evaluation_output.interviewing_skills
        ]
        
        if missing_skills:
            validation_results["quality_issues"].append(f"Missing interviewing skills: {missing_skills}")
        
        # Check completeness
        completeness_factors = [
            ("job_matching_score", 0.0 <= evaluation_output.job_matching_score <= 10.0),
            ("interviewing_skills", len(evaluation_output.interviewing_skills) >= 5),
            ("skill_assessments", len(evaluation_output.skill_assessments) >= 3),
            ("strengths", len(evaluation_output.strengths) >= 2),
            ("improvement_areas", len(evaluation_output.improvement_areas) >= 2),
            ("overall_feedback", len(evaluation_output.overall_feedback) > 50),
            ("recommendations", len(evaluation_output.recommendations) >= 3),
            ("interview_readiness", 0.0 <= evaluation_output.interview_readiness <= 10.0)
        ]
        
        completed_factors = sum(1 for _, completed in completeness_factors if completed)
        validation_results["completeness_score"] = completed_factors / len(completeness_factors)
        
        # Check for generic feedback
        if "evaluation completed" in evaluation_output.overall_feedback.lower():
            validation_results["quality_issues"].append("Generic overall feedback")
            validation_results["recommendations"].append("Provide more specific and personalized feedback")
        
        # Mark as invalid if critical issues found
        if validation_results["completeness_score"] < 0.8:
            validation_results["is_valid"] = False
        
        return validation_results
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the ISA_Evaluator agent"""
        return {
            "agent_name": "ISA_Evaluator",
            "description": "Interview assessment and feedback agent",
            "model": self.model_name,
            "capabilities": [
                "Job matching assessment (0-10 scale)",
                "Interviewing skills evaluation (5 dimensions)",
                "Individual skill assessments",
                "Strengths and improvement identification",
                "Comprehensive feedback generation",
                "Interview readiness scoring",
                "Detailed feedback reports"
            ],
            "evaluation_dimensions": [
                "Clear & Concise Communication",
                "Confidence & Professionalism",
                "Active Listening",
                "Thoughtful & Relevant Responses",
                "Adaptability & Problem-Solving"
            ],
            "scoring_scale": "1-10 (1=Poor, 5=Average, 10=Excellent)",
            "output_format": "EvaluationOutput",
            "report_generation": "Detailed candidate feedback reports",
            "status": "active" if self.model else "inactive"
        }
