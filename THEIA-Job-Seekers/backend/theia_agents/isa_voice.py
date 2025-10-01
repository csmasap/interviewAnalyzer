"""
ISA_Prep_Voice Agent - Real-time Voice Interview Agent
OpenAI Realtime API agent for conducting voice-to-voice interviews.
"""

import asyncio
import logging
import json
import base64
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable
from datetime import datetime
import websockets
import ssl

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import (
    VoiceSessionConfig, 
    VoiceResponse, 
    QuestionGenerationOutput,
    SkillsDetectionOutput,
    InterviewSession
)
from config import settings

logger = logging.getLogger(__name__)


class ISAPrepVoice:
    """
    ISA_Prep_Voice Agent
    
    Conducts real-time voice interviews using OpenAI's Realtime API:
    - Voice-to-voice conversation with natural flow
    - Real-time audio processing and response
    - Integration with text-based agents for consistent evaluation
    - WebRTC support for low-latency communication
    - Seamless question delivery and answer collection
    """
    
    def __init__(self):
        """Initialize the ISA_Prep_Voice agent"""
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_REALTIME_MODEL
        self.websocket_url = "wss://api.openai.com/v1/realtime"
        
        # Voice session configuration
        self.voice_config = VoiceSessionConfig()
        
        # Session state
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"✅ ISA_Prep_Voice initialized with model: {self.model}")
    
    async def start_voice_interview_session(
        self,
        session_id: str,
        prepared_context: Dict[str, Any],
        on_response: Optional[Callable] = None,
        on_question_complete: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Start a voice interview session using prepared context from prepare endpoint
        
        Args:
            session_id: Unique session identifier
            prepared_context: Complete context from prepare endpoint including questions, company info, skills, etc.
            on_response: Callback for voice responses
            on_question_complete: Callback when question is answered
            
        Returns:
            Dict with session information and connection details
        """
        logger.info(f"🎤 Starting voice interview session: {session_id}")
        
        try:
            # Extract questions from prepared context
            # Questions come in format: [{"id": "q1", "text": "..."}, {"id": "q2", "text": "..."}, ...]
            question_objects = prepared_context.get("question_plan", [])
            if not question_objects:
                question_objects = prepared_context.get("questions", [])
            
            # Extract text from question objects
            questions = []
            if question_objects:
                for q in question_objects:
                    if isinstance(q, dict):
                        # Extract text field from question object
                        question_text = q.get("text", "")
                        if question_text:
                            questions.append(question_text)
                        else:
                            logger.warning(f"Question object missing 'text' field: {q}")
                    else:
                        # Fallback for string questions
                        questions.append(str(q))
            
            if not questions:
                logger.error(f"No valid questions found in prepared context. question_plan: {question_objects}")
                raise ValueError("No questions found in prepared context")
            
            # Initialize session state with prepared context
            session_state = {
                "session_id": session_id,
                "prepared_context": prepared_context,
                "questions": questions,
                "current_question_index": 0,
                "answers": [],
                "transcript": [],
                "status": "initializing",
                "websocket": None,
                "phase": "greeting",
                "callbacks": {
                    "on_response": on_response,
                    "on_question_complete": on_question_complete
                },
                "created_at": datetime.utcnow(),
                "voice_config": self.voice_config
            }
            
            self.active_sessions[session_id] = session_state
            
            # Connect to OpenAI Realtime API
            await self._connect_to_realtime_api(session_id)
            
            # Initialize the interview with prepared context
            await self._initialize_voice_interview(session_id)
            
            logger.info(f"✅ Voice interview session started: {session_id}")
            
            return {
                "session_id": session_id,
                "status": "active",
                "voice_config": self.voice_config.dict(),
                "total_questions": len(questions),
                "interview_mode": "voice"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to start voice interview session {session_id}: {e}")
            # Clean up failed session
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            raise
    
    async def _connect_to_realtime_api(self, session_id: str) -> None:
        """Connect to OpenAI Realtime API WebSocket"""
        session_state = self.active_sessions[session_id]
        
        try:
            # Create SSL context
            ssl_context = ssl.create_default_context()
            
            # Headers for authentication
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            # Connect to WebSocket
            websocket = await websockets.connect(
                f"{self.websocket_url}?model={self.model}",
                extra_headers=headers,
                ssl=ssl_context
            )
            
            session_state["websocket"] = websocket
            session_state["status"] = "connected"
            
            # Start message handling
            asyncio.create_task(self._handle_realtime_messages(session_id))
            
            logger.info(f"✅ Connected to OpenAI Realtime API for session: {session_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Realtime API for session {session_id}: {e}")
            raise
    
    async def _initialize_voice_interview(self, session_id: str) -> None:
        """Initialize the voice interview with system instructions"""
        session_state = self.active_sessions[session_id]
        prepared_context = session_state["prepared_context"]
        
        # Extract information from prepared context
        company_name = prepared_context.get("company", "the company")
        job_title = prepared_context.get("job_title", "this position")
        
        system_instructions = self._create_voice_system_instructions(
            job_title,
            company_name,
            session_state["questions"],
            prepared_context,
        )
        
        # Send session configuration
        config_message = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": system_instructions,
                "voice": "alloy",  # OpenAI voice model
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": self.voice_config.vad_threshold,
                    "prefix_padding_ms": self.voice_config.prefix_padding_ms,
                    "silence_duration_ms": self.voice_config.silence_duration_ms
                },
                "tools": [],
                "tool_choice": "none",
                "temperature": 0.6,
                "max_response_output_tokens": 4096
            }
        }
        
        await self._send_realtime_message(session_id, config_message)
        
        # Wait a moment for session to be ready
        await asyncio.sleep(0.5)
        
        # ISA speaks first - deliver immediate greeting
        await self._deliver_initial_greeting_immediately(session_id)

    async def _deliver_initial_greeting_immediately(self, session_id: str) -> None:
        """Make ISA speak first immediately upon connection with greeting"""
        session_state = self.active_sessions[session_id]
        prepared_context = session_state["prepared_context"]

        # Create personalized greeting using prepared context
        greeting_text = self._create_greeting_text(
            prepared_context.get("job_title", "this position"),
            prepared_context.get("company", "the company"),
            prepared_context
        )

        # Create a conversation item that ISA will speak immediately
        greeting_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "assistant",  # ISA is the assistant speaking
                "content": [
                    {"type": "text", "text": greeting_text}
                ]
            }
        }
        await self._send_realtime_message(session_id, greeting_message)

        # Immediately create a response to speak the greeting
        response_message = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
                "instructions": "Speak this greeting warmly and professionally. Wait for the user's response about whether they want insights first or to start immediately."
            }
        }
        await self._send_realtime_message(session_id, response_message)

        session_state["phase"] = "greeting_response"
        logger.info(f"🎤 ISA delivered immediate greeting for session {session_id}")

    async def _deliver_initial_greeting(self, session_id: str) -> None:
        """Deliver ISA's initial greeting and offer insights option"""
        session_state = self.active_sessions[session_id]
        prepared_context = session_state["prepared_context"]

        # Create personalized greeting using prepared context
        greeting_text = self._create_greeting_text(
            prepared_context.get("job_title", "this position"),
            prepared_context.get("company", "the company"),
            prepared_context
        )

        greeting_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": greeting_text}
                ]
            }
        }
        await self._send_realtime_message(session_id, greeting_message)

        response_message = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
                "instructions": "Deliver this greeting warmly and professionally. Then wait for whether the user wants insights first or to start immediately."
            }
        }
        await self._send_realtime_message(session_id, response_message)

        session_state["phase"] = "greeting_response"

    def _create_greeting_text(self, job_title: str, company_name: str, prepared_context: Dict[str, Any]) -> str:
        # Extract candidate name for personalization
        candidate_name = prepared_context.get("candidate_name", "")
        first_name = prepared_context.get("first_name", "")
        if not first_name and candidate_name:
            first_name = candidate_name.split()[0] if candidate_name else ""
        
        # Extract skills from prepared context
        skills = prepared_context.get("detected_skills", [])
        if not skills:
            skills = prepared_context.get("key_skills", [])
        
        skills_mention = ""
        if skills:
            top = skills[:3]
            if len(top) == 1:
                skills_mention = f" I notice you'll be focusing on {top[0]} skills."
            elif len(top) == 2:
                skills_mention = f" I notice you'll be focusing on {top[0]} and {top[1]} skills."
            else:
                skills_mention = f" I notice you'll be focusing on {', '.join(top[:-1])}, and {top[-1]} skills."

        greeting_name = f"Hello {first_name}!" if first_name else "Hello!"
        
        return (
            f"{greeting_name} I'm ISA - your Interview Smart Agent. It's great to meet you!\n\n"
            f"I'm here to help you prepare for your {job_title} interview at {company_name}.{skills_mention}\n\n"
            "I have everything ready for your mock interview preparation session. I've prepared specific questions based on the role requirements and your background, and I've analyzed the interview approach that would be most effective.\n\n"
            "Would you like to start with the interview right away, or would you prefer to first hear my insights about what to expect and how to approach the questions?\n\n"
            "Just let me know - would you like insights first, or shall we jump straight into the interview?"
        )

    async def _deliver_insights(self, session_id: str) -> None:
        session_state = self.active_sessions[session_id]
        prepared_context = session_state["prepared_context"]
        questions = session_state["questions"]

        insights_text = self._generate_insights_text(
            prepared_context.get("job_title", "this position"),
            prepared_context.get("company", "the company"),
            questions,
            prepared_context
        )

        insights_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": insights_text}
                ]
            }
        }
        await self._send_realtime_message(session_id, insights_message)

        response_message = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
                "instructions": "Share these insights thoughtfully. Then say 'Well, let's start with your interview preparation...' and proceed to the first question."
            }
        }
        await self._send_realtime_message(session_id, response_message)

        session_state["phase"] = "insights_to_interview"

    async def _transition_to_interview(self, session_id: str) -> None:
        transition_text = (
            "Perfect! Let's get started with your interview preparation. I'll ask you the questions and you can practice your responses. Ready? Here's your first question:"
        )
        transition_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": transition_text}
                ]
            }
        }
        await self._send_realtime_message(session_id, transition_message)

        response_message = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
                "instructions": "Acknowledge the transition and ask the first interview question clearly and professionally."
            }
        }
        await self._send_realtime_message(session_id, response_message)

        await self._ask_next_question(session_id)

    def _generate_insights_text(self, job_title: str, company_name: str, questions: List[str], prepared_context: Dict[str, Any]) -> str:
        # Extract data from prepared context
        skills = prepared_context.get("detected_skills", [])
        if not skills:
            skills = prepared_context.get("key_skills", [])
        
        interview_style = prepared_context.get("interview_style")
        company_info = prepared_context.get("market_intelligence", {})
        research = prepared_context.get("research", {})
        
        insights = []

        question_types = self._analyze_question_types(questions)
        if question_types:
            insights.append(f"Based on my analysis of your prepared questions, you'll encounter {question_types}.")

        if skills:
            top_skills = ", ".join(skills[:3])
            insights.append(f"The interview will focus heavily on {top_skills} skills. I've prepared questions that will let you demonstrate these capabilities with specific examples.")

        # Use research insights
        if research.get("interview_style"):
            insights.append(f"The company's interview style tends to be {research['interview_style']}.")
        
        if research.get("common_questions"):
            insights.append("I've incorporated knowledge of their typical question patterns into your preparation.")

        if interview_style:
            if "technical" in interview_style.lower():
                insights.append("Expect technical deep dives; walk through your problem-solving process step by step.")
            if "behavioral" in interview_style.lower():
                insights.append("Use the STAR method (Situation, Task, Action, Result) for behavioral questions.")

        # General tips
        insights.append("Take your time to think before responding; thoughtful pauses show you're being thoughtful.")
        insights.append("Use specific, quantified examples from your experience where possible.")
        insights.append("Remember, this is practice - focus on authenticity and clear communication.")

        return (
            f"Perfect! Let me share my insights about your {job_title} interview at {company_name}.\n\n"
            + " ".join(insights)
            + "\n\nAlright, I think you're ready! Let's begin with your first prepared question."
        )

    def _analyze_question_types(self, questions: List[str]) -> str:
        if not questions:
            return "a mix of different question types"
        behavioral_count = sum(1 for q in questions if any(w in q.lower() for w in ["tell me about", "describe", "experience", "time when", "example"]))
        technical_count = sum(1 for q in questions if any(w in q.lower() for w in ["how would", "design", "implement", "solve", "technical", "algorithm"]))
        situational_count = sum(1 for q in questions if any(w in q.lower() for w in ["what would you", "if you", "scenario", "situation"]))
        total = len(questions)
        parts: List[str] = []
        if behavioral_count > total * 0.3:
            parts.append("behavioral questions focusing on past experiences")
        if technical_count > total * 0.3:
            parts.append("technical questions about problem-solving")
        if situational_count > total * 0.3:
            parts.append("situational questions about hypothetical scenarios")
        if not parts:
            return "a mix of different question types"
        if len(parts) == 1:
            return f"primarily {parts[0]}"
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return f"{', '.join(parts[:-1])}, and {parts[-1]}"
    
    def _create_voice_system_instructions(
        self,
        job_title: str,
        company_name: str,
        questions: List[str],
        prepared_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create system instructions for the voice interview using prepared context"""
        
        # Extract comprehensive context
        skills = []
        style = None
        candidate_name = ""
        
        if prepared_context and isinstance(prepared_context, dict):
            skills = prepared_context.get("detected_skills", []) or prepared_context.get("key_skills", [])
            style = prepared_context.get("interview_style")
            candidate_name = prepared_context.get("candidate_name", "")
            
        skills_str = ", ".join(skills[:6]) if skills else "general skills"
        first_name = candidate_name.split()[0] if candidate_name else ""

        instructions = f"""
You are ISA (Interview Smart Agent), a professional and friendly AI interviewer conducting a mock interview preparation session.

CRITICAL BEHAVIOR - YOU SPEAK FIRST:
- You are the interviewer and you initiate all conversations
- When the session starts, you immediately greet the candidate
- You do NOT wait for the candidate to speak first
- You control the flow of the interview

INTERVIEW CONTEXT:
- Position: {job_title}
- Company: {company_name}
- Candidate: {candidate_name or 'the candidate'}
- First Name: {first_name}
- Interview Type: Mock interview for preparation using prepared questions
- Format: Voice conversation
- Prepared Questions: {len(questions)} specific questions based on role analysis

MANDATORY - USE ONLY PREPARED QUESTIONS:
- You have exactly {len(questions)} specifically prepared questions
- These questions were generated based on job requirements, company research, and candidate background
- DO NOT create, modify, or improvise questions - use ONLY the prepared questions in order
- Each question targets specific competencies for this role
- Questions are numbered q1 through q{len(questions)}

YOUR ROLE:
- Speak first with a warm, professional greeting
- Conduct the mock interview using ONLY the prepared questions
- Ask each prepared question clearly and conversationally
- Listen actively to responses
- Provide brief acknowledgments between questions
- Maintain a supportive but professional tone

CONVERSATION FLOW:
1. YOU SPEAK FIRST: Greet {first_name or 'the candidate'} and offer insights or immediate start
2. If candidate wants insights, share analysis about interview approach and question types
3. Then proceed through the prepared questions one by one in order
4. Ask each question exactly as prepared - no modifications
5. Allow complete responses before moving to next question

CONVERSATION STYLE:
- Speak naturally and conversationally
- Use a warm, professional tone
- Keep questions clear and well-paced
- Allow time for thoughtful responses
- Provide brief encouraging acknowledgments ("That's a great example", "I appreciate the detail")
- Address candidate by name ({first_name}) when appropriate

CRITICAL GUIDELINES:
- YOU initiate every phase of the conversation
- This is PRACTICE - be supportive and encouraging
- ONLY ask the prepared questions - absolutely no improvisation
- Ask questions one at a time and wait for COMPLETE answers
- Allow time for thinking - thoughtful pauses are good
- Keep your responses concise to let candidate speak more
- Focus on realistic interview simulation
- Don't provide detailed feedback during questions - save for end
- Stay professional but encouraging throughout

PREPARED CONTEXT:
- Focus skills: {skills_str}
- Interview style: {style or 'Professional assessment'}
- Questions are tailored specifically for {candidate_name or 'this candidate'} and this {job_title} role

Remember: You are the interviewer. You speak first. You control the conversation flow. Use only the prepared questions.
"""
        return instructions
    
    async def _handle_realtime_messages(self, session_id: str) -> None:
        """Handle incoming messages from OpenAI Realtime API"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        websocket = session_state["websocket"]
        
        try:
            async for message in websocket:
                await self._process_realtime_message(session_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 Realtime API connection closed for session: {session_id}")
            session_state["status"] = "disconnected"
        except Exception as e:
            logger.error(f"❌ Error handling realtime messages for session {session_id}: {e}")
            session_state["status"] = "error"
    
    async def _process_realtime_message(self, session_id: str, message: str) -> None:
        """Process individual message from OpenAI Realtime API"""
        try:
            data = json.loads(message)
            message_type = data.get("type", "")
            
            session_state = self.active_sessions.get(session_id)
            if not session_state:
                return
            
            # Handle different message types
            if message_type == "session.created":
                logger.info(f"✅ Realtime session created: {session_id}")
                session_state["status"] = "active"
                
            elif message_type == "conversation.item.input_audio_transcription.completed":
                # User's speech was transcribed
                transcript = data.get("transcript", "")
                await self._handle_user_response(session_id, transcript)
                
            elif message_type == "response.audio.delta":
                # AI is speaking - stream audio
                audio_data = data.get("delta", "")
                await self._handle_ai_audio_response(session_id, audio_data)
                
            elif message_type == "response.done":
                # AI finished responding
                await self._handle_response_complete(session_id, data)
                
            elif message_type == "error":
                logger.error(f"❌ Realtime API error for session {session_id}: {data}")
                session_state["status"] = "error"
                
        except Exception as e:
            logger.error(f"❌ Error processing realtime message for session {session_id}: {e}")
    
    async def _handle_user_response(self, session_id: str, transcript: str) -> None:
        """Handle user's transcribed response based on conversation phase"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return

        current_phase = session_state.get("phase", "interview")

        if current_phase == "greeting_response":
            # Decide between insights or immediate start
            transcript_lower = transcript.lower()
            wants_insights = any(word in transcript_lower for word in [
                "insights", "hear", "first", "guidance", "advice", "tips",
                "approach", "strategy", "prepare", "help", "understand"
            ])
            wants_immediate = any(word in transcript_lower for word in [
                "start", "begin", "immediate", "now", "go", "proceed", "skip"
            ])

            # Log user's choice
            session_state["transcript"].append({
                "type": "user",
                "content": transcript,
                "phase": "greeting_response",
                "timestamp": datetime.utcnow().isoformat()
            })

            if wants_insights and not wants_immediate:
                session_state["phase"] = "insights"
                await self._deliver_insights(session_id)
            else:
                session_state["phase"] = "interview"
                await self._transition_to_interview(session_id)

            return

        # Default: interview phase handling
        current_index = session_state["current_question_index"]
        session_state["answers"].append(transcript)
        session_state["transcript"].append({
            "type": "user",
            "content": transcript,
            "question_index": current_index,
            "phase": "interview",
            "timestamp": datetime.utcnow().isoformat()
        })

        callback = session_state["callbacks"].get("on_question_complete")
        if callback:
            try:
                await callback(session_id, current_index, transcript)
            except Exception as e:
                logger.error(f"❌ Error in question complete callback: {e}")

        logger.info(f"📝 Recorded answer for question {current_index + 1} in session {session_id}")
    
    async def _handle_ai_audio_response(self, session_id: str, audio_data: str) -> None:
        """Handle AI audio response"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        # Decode base64 audio data
        try:
            audio_bytes = base64.b64decode(audio_data)
            
            # Stream audio to callback if provided
            callback = session_state["callbacks"].get("on_response")
            if callback:
                try:
                    voice_response = VoiceResponse(
                        audio_data=audio_bytes,
                        transcript="",  # Will be filled when complete
                        is_question=True,
                        metadata={"session_id": session_id}
                    )
                    await callback(voice_response)
                except Exception as e:
                    logger.error(f"❌ Error in audio response callback: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Error handling AI audio response: {e}")
    
    async def _handle_response_complete(self, session_id: str, response_data: Dict[str, Any]) -> None:
        """Handle completion of AI response"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        # Extract response content and transcript
        response_content = ""
        for item in response_data.get("response", {}).get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "text":
                        response_content += content.get("text", "")
        
        # Add AI response to transcript with phase context
        current_phase = session_state.get("phase", "interview")
        session_state["transcript"].append({
            "type": "ai",
            "content": response_content,
            "question_index": session_state["current_question_index"],
            "phase": current_phase,
            "timestamp": datetime.utcnow().isoformat()
        })

        # After AI finishes: if we just delivered insights, move to interview; else normal progression
        if current_phase == "insights_to_interview":
            session_state["phase"] = "interview"
            await self._ask_next_question(session_id)
        elif current_phase == "interview":
            await self._check_interview_progress(session_id)
    
    async def _ask_next_question(self, session_id: str) -> None:
        """Ask the next question in the interview"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        current_index = session_state["current_question_index"]
        questions = session_state["questions"]
        
        if current_index < len(questions):
            question = questions[current_index]
            
            # Create question message
            question_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Please ask this question: {question}"
                        }
                    ]
                }
            }
            
            await self._send_realtime_message(session_id, question_message)
            
            # Trigger response
            response_message = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio"],
                    "instructions": "Ask the provided question clearly and conversationally, then wait patiently for the candidate's complete response. Allow time for thinking and thorough answers."
                }
            }
            
            await self._send_realtime_message(session_id, response_message)
            
            logger.info(f"🎤 Asked question {current_index + 1}/{len(questions)} in session {session_id}")
        else:
            # Interview complete
            await self._complete_voice_interview(session_id)
    
    async def _check_interview_progress(self, session_id: str) -> None:
        """Check interview progress and move to next question if ready"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        current_index = session_state["current_question_index"]
        answers_count = len(session_state["answers"])
        
        # If we have an answer for the current question, move to next
        if answers_count > current_index:
            session_state["current_question_index"] += 1
            
            # Brief pause before next question to allow natural flow
            await asyncio.sleep(3)
            
            # Ask next question
            await self._ask_next_question(session_id)
    
    async def _complete_voice_interview(self, session_id: str) -> None:
        """Complete the voice interview session"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        # Send completion message
        completion_message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Thank you for completing the mock interview. Your responses have been recorded and you'll receive detailed feedback shortly to help you prepare for your actual interview."
                    }
                ]
            }
        }
        
        await self._send_realtime_message(session_id, completion_message)
        
        # Trigger final response
        final_response = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
                "instructions": "Provide a warm, encouraging closing message for the mock interview."
            }
        }
        
        await self._send_realtime_message(session_id, final_response)
        
        # Update session status
        session_state["status"] = "completed"
        session_state["completed_at"] = datetime.utcnow()
        
        logger.info(f"✅ Voice interview completed for session: {session_id}")
    
    async def _send_realtime_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Send message to OpenAI Realtime API"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        websocket = session_state.get("websocket")
        if not websocket:
            logger.error(f"❌ No websocket connection for session: {session_id}")
            return
        
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"❌ Error sending realtime message for session {session_id}: {e}")
    
    async def end_voice_interview_session(self, session_id: str) -> Dict[str, Any]:
        """End a voice interview session and return results"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return {"error": "Session not found"}
        
        try:
            # Close WebSocket connection
            websocket = session_state.get("websocket")
            if websocket:
                await websocket.close()
            
            # Prepare session results
            results = {
                "session_id": session_id,
                "status": session_state["status"],
                "questions_asked": len(session_state["answers"]),
                "total_questions": len(session_state["questions"]),
                "answers": session_state["answers"],
                "transcript": session_state["transcript"],
                "duration": (
                    datetime.utcnow() - session_state["created_at"]
                ).total_seconds(),
                "completed_at": session_state.get("completed_at"),
                "interview_mode": "voice"
            }
            
            # Clean up session
            del self.active_sessions[session_id]
            
            logger.info(f"🏁 Voice interview session ended: {session_id}")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error ending voice interview session {session_id}: {e}")
            return {"error": str(e)}
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get current status of a voice interview session"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return {"error": "Session not found"}
        
        return {
            "session_id": session_id,
            "status": session_state["status"],
            "current_question_index": session_state["current_question_index"],
            "questions_completed": len(session_state["answers"]),
            "total_questions": len(session_state["questions"]),
            "created_at": session_state["created_at"].isoformat(),
            "interview_mode": "voice"
        }
    
    async def process_audio_input(
        self,
        session_id: str,
        audio_data: bytes,
        sample_rate: int = 16000
    ) -> None:
        """Process audio input from the user"""
        session_state = self.active_sessions.get(session_id)
        if not session_state:
            return
        
        try:
            # Convert audio to base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Send audio to Realtime API
            audio_message = {
                "type": "input_audio_buffer.append",
                "audio": audio_b64
            }
            
            await self._send_realtime_message(session_id, audio_message)
            
        except Exception as e:
            logger.error(f"❌ Error processing audio input for session {session_id}: {e}")
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active voice interview sessions"""
        return list(self.active_sessions.keys())
    
    async def start_voice_session_with_prepare_endpoint(
        self,
        session_id: str,
        on_response: Optional[Callable] = None,
        on_question_complete: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Start a voice interview session by fetching prepared context from prepare endpoint
        
        This is a convenience method that calls the prepare endpoint and then starts the voice session.
        This is the recommended way to start voice interviews as it ensures all context is properly loaded.
        
        Args:
            session_id: Unique session identifier
            on_response: Callback for voice responses
            on_question_complete: Callback when question is answered
            
        Returns:
            Dict with session information and connection details
        """
        try:
            # Import here to avoid circular dependencies
            import json
            import urllib.request as urllib_request
            
            # Call prepare endpoint to get comprehensive context
            # This would typically be an internal API call in production
            prepare_url = f"http://localhost:8000/api/v1/voice/{session_id}/prepare"
            
            try:
                req = urllib_request.Request(prepare_url, method="POST")
                with urllib_request.urlopen(req, timeout=10) as response:
                    prepare_data = json.loads(response.read().decode('utf-8'))
                    
                if prepare_data.get("error"):
                    raise ValueError(f"Prepare endpoint error: {prepare_data['error']}")
                    
                prepared_context = prepare_data.get("context", {})
                
            except Exception as e:
                logger.error(f"❌ Failed to fetch prepared context for session {session_id}: {e}")
                # Fallback to empty context - this should be handled gracefully
                prepared_context = {"error": f"Failed to fetch prepared context: {e}"}
            
            # Start voice session with prepared context
            return await self.start_voice_interview_session(
                session_id=session_id,
                prepared_context=prepared_context,
                on_response=on_response,
                on_question_complete=on_question_complete
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to start voice session with prepare endpoint for {session_id}: {e}")
            raise
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the ISA_Prep_Voice agent"""
        return {
            "agent_name": "ISA_Prep_Voice",
            "description": "Real-time voice interview agent using OpenAI Realtime API with prepared context",
            "model": self.model,
            "capabilities": [
                "Voice-to-voice interview conversations",
                "Real-time audio processing",
                "Natural conversation flow",
                "Prepared question delivery based on role analysis",
                "Interview transcript generation",
                "WebRTC support for low latency",
                "Personalized greetings and insights"
            ],
            "audio_formats": [
                "PCM16 input/output",
                "16kHz sample rate",
                "Mono channel audio"
            ],
            "features": [
                "Server-side voice activity detection",
                "Automatic speech transcription",
                "Natural conversation pacing",
                "Professional interview simulation",
                "Real-time feedback capability",
                "Uses prepared context from prepare endpoint",
                "Offers insights before starting interview",
                "Personalized candidate experience"
            ],
            "integration": "Uses prepared context from /api/v1/voice/{session_id}/prepare endpoint",
            "active_sessions": len(self.active_sessions),
            "status": "active" if self.api_key else "inactive",
            "version": "2.0 - Updated to use prepare endpoint"
        }


