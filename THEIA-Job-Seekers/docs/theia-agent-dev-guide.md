# THEIA Interview Prep - Developer Guide and Change Log

This document summarizes the changes implemented across the backend and frontend, and provides a concise guide for new contributors to understand, run, and extend the system.

## Contents
- Overview
- Environment and Models
- Backend changes (by file)
- Frontend changes
- Testing (unit + live Vertex)
- Running locally
- Logging and troubleshooting
- Extension points and next steps

---

## Overview
We refactored the THEIA Interview Prep system to make the Text Interview flow robust, fast, and developer-friendly:
- Standardized all agents to read model names from `.env` via `config.settings`.
- Added resilient conversation handling in `simple_main.py` so the chat works without WebSocket and always returns the next question.
- Hardened JSON parsing for agents, added timeouts, lowered temperatures, and reduced token budgets to prevent truncation.
- Switched web-grounding to prefer Vertex `google_search` (with enterprise web search fallback if available).
- Created shared JSON utilities and added high-signal logs to quickly diagnose issues.
- Frontend now always shows the first question, gracefully fetches the next one, and auto-scrolls to the latest message.

---

## Environment and Models
File: `/Users/fernandoponce/interviewAnalyzer/.env`

Key variables (all read by `config.settings`):
- `GOOGLE_CLOUD_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS`
- `VERTEX_AI_MODEL` (pro path)
- `VERTEX_AI_MODEL_FAST` (flash path)
- `VERTEX_AI_LOCATION`

Recommended split:
- `VERTEX_AI_MODEL=gemini-2.5-pro`
- `VERTEX_AI_MODEL_FAST=gemini-2.5-flash`

The chat agent (`ISAChat`) now defaults to `VERTEX_AI_MODEL_FAST` (fast), while Detector/Questioner/Researcher/Evaluator use the appropriate pro/flash based on complexity via the base agent.

---

## Backend changes (by file)

### 1) `external/THEIA-Job-Seekers/backend/simple_main.py`
- Text Interview answer endpoint (`/api/v1/interviews/{session_id}/answer`):
  - Builds an `InterviewSession` with safe phase fallback (`INTERVIEW_ACTIVE → INTERVIEW → "interview"`).
  - Persists `current_question_index` and appends structured answers: `{question_id, question_text, answer_text, timestamp}`.
  - If no answer is provided, returns the current question (`question_ready`) immediately.
  - If an answer is provided, acknowledges (model-driven via `ISAChat`, heuristic fallback), advances the index, and returns `ai.next_question`.
  - Adds defensive fallbacks (“manual fallback answer_recorded …”) so conversation continues even if the model path fails.
  - Adds diagnostic logs:
    - `/answer entry …`, `state …`, `question_ready …`, `answer_recorded …`, and bottom fallback state logs.
  - Upgraded error handling to `logger.exception(...)` so stack traces are visible.
- General: converts Pydantic outputs later (note: deprecation warnings remain in older spots; see TODO).

### 2) `external/THEIA-Job-Seekers/backend/theia_agents/isa_chat.py`
- Reads model from `.env` via `settings` and uses `VERTEX_AI_MODEL_FAST` (fallback to `VERTEX_AI_MODEL`).
- Adds safe WebSocket stub when `websocket.manager` is unavailable (local dev).
- Validates/acknowledges answers using the model; if the model echoes the answer, synthesizes concise feedback via a heuristic validator.
- `generate_questions_from_job_description` creates a 10-question JSON schema with guardrails.

### 3) `external/THEIA-Job-Seekers/backend/theia_agents/isa_researcher.py`
- Prompts include CRITICAL OUTPUT RULES and a minimal JSON example.
- Web grounding order: Vertex `google_search` preferred → enterprise web search fallback → plain model.
- Structured-first parse using shared utils; if parsing fails, wraps raw text into `ResearchOutput` (`company_info["raw_text"]`).
- Reduced token budgets and temperatures for determinism.

### 4) `external/THEIA-Job-Seekers/backend/theia_agents/isa_detector.py`
- Uses shared JSON utilities to extract balanced JSON and remove trailing commas.
- Adds web grounding with fallbacks similar to Researcher.
- Tight token budgets and low temperature for schema stability.

### 5) `external/THEIA-Job-Seekers/backend/theia_agents/isa_questioner.py`
- Similar parsing hardening and grounding strategy.
- Ensures exactly 10 questions; pads rationale/difficulty/types as needed.

### 6) `external/THEIA-Job-Seekers/backend/utils/json_utils.py` (new)
- `strip_code_fences(text)`
- `extract_first_balanced_json(text) -> (json_substring, ok)`
- `try_parse_json(text)` → retries after removing trailing commas.

### 7) `external/THEIA-Job-Seekers/backend/config/settings.py`
- Centralizes `.env` access for `VERTEX_AI_MODEL`, `VERTEX_AI_MODEL_FAST`, etc.
- Flexible `ALLOWED_ORIGINS` parsing (JSON array or comma-separated).

---

## Frontend changes
File: `external/THEIA-Job-Seekers/frontend/theia-frontend/public/interview.html`
- API base discovery and status probe retained.
- Start Interview flow:
  1) Start session → 2) Generate questions → 3) Open Text modal → 4) Request first question.
- If `/answer` does not include `ai.next_question`, falls back to the list returned by `/generate_questions`.
- Submitting an empty answer now triggers a fetch for the next question (useful for kick-offs).
- Auto-scrolls to the latest message after each append and re-focuses the input box for fast typing.

---

## Testing

### Unit-like integration (no Vertex calls):
- `tests/test_isa_chat_integration.py` — forces `chat.model=None` and verifies:
  - Index advances on each turn
  - Answers/transcript recorded
  - Completion at last question

Run:
```bash
PYTHONPATH="external/THEIA-Job-Seekers/backend" external/THEIA-Job-Seekers/venv/bin/pytest tests/test_isa_chat_integration.py -q
```

### Live Vertex AI integration:
- `tests/test_isa_chat_ai_integration_vertex.py` — skipped unless `RUN_AI_TESTS=1` and Vertex env available; generates questions and validates feedback roundtrip.

Run:
```bash
set -a; source .env; set +a
RUN_AI_TESTS=1 PYTHONPATH="external/THEIA-Job-Seekers/backend" \
  external/THEIA-Job-Seekers/venv/bin/pytest tests/test_isa_chat_ai_integration_vertex.py -q
```

---

## Running locally
Use the provided script which frees ports and launches backend and frontend:
```bash
external/THEIA-Job-Seekers/start_full_system.sh
```
Notes:
- If logs don’t update, ensure the prior backend process is terminated: `lsof -ti tcp:8000 | xargs -r kill -9` and re-run the script.
- The backend runs as a background process; restart to pick up code changes.

---

## Logging and troubleshooting
- Look for these lines in backend logs during the Text flow:
  - `ISA_Chat: /answer entry …`
  - `ISA_Chat: state …` (branch state snapshot)
  - `ISA_Chat: question_ready …` or `fallback question_ready …`
  - `ISA_Chat: answer_recorded prev_index=… next_index=… next_q_present=…`
  - `manual fallback answer_recorded …` or `bottom fallback …` if needed
- Common issues:
  - Missing next question: Check `current_question_index` persistence and session `questions` count.
  - Enum mismatch: phase fallback added (INTERVIEW_ACTIVE / INTERVIEW / string).
  - Web grounding 403: ensure Vertex AI API is enabled and service account has `roles/aiplatform.user`.

---

## Extension points and next steps
- Pydantic v2 deprecations:
  - Replace remaining `.dict()` and `@validator` with `.model_dump()` and `@field_validator`.
- Move remaining JSON parsing (e.g., in `isa_chat` validation) to `json_utils` for consistency.
- Consider a lightweight session store (Redis) for multi-instance robustness.
- Add e2e UI test for first-question kick-off and auto-scroll.
- Add structured telemetry for agent-path selection (flash vs pro, grounded vs plain).

---

## Quick reference - Key files touched
- Backend
  - `backend/simple_main.py` (Text interview endpoints)
  - `backend/theia_agents/isa_chat.py` (chat flow, model selection)
  - `backend/theia_agents/isa_researcher.py` (grounding, parsing)
  - `backend/theia_agents/isa_detector.py` (grounding, parsing)
  - `backend/theia_agents/isa_questioner.py` (grounding, parsing)
  - `backend/utils/json_utils.py` (new)
  - `backend/config/settings.py` (env + models)
- Frontend
  - `frontend/theia-frontend/public/interview.html` (kick-off, empty-submit handling, auto-scroll)
- Tests
  - `tests/test_isa_chat_integration.py`
  - `tests/test_isa_chat_ai_integration_vertex.py`

This guide should enable new contributors to understand the current architecture, reproduce the local environment, and continue development with confidence.

