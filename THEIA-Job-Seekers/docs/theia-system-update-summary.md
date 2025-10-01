## THEIA Interview Prep System – Backend and Frontend Updates

### Date
2025-09-30

### Overview
Consolidated the backend to a single FastAPI app, simplified environment/startup, improved Salesforce skills endpoint, and streamlined the frontend. Legacy static routes required for marketing/demo were restored with a simple navigation menu.

---

### Backend (external/THEIA-Job-Seekers/backend)

1) Consolidation to simple_main.py
- Kept `backend/simple_main.py` as the canonical app.
- Removed the router-based duplicate stack (fewer moving parts, simpler deploy).

2) Merged and enhanced Skills endpoint
- `/api/v1/skills` in `simple_main.py` now:
  - Discovers skill/score fields dynamically via `describe()`
  - Reads from both `THEIA_Interview__c` and `TR1__Opportunity_Discussed__c`
  - Deduplicates skills by name and returns most recent entries

3) Removed redundant/unused code
- Deleted `backend/api/**` (routers/endpoints), `backend/main_backup.py`
- Deleted `backend/websocket/**` and `backend/utils/memory.py` (not used by consolidated app)
- Deleted `backend/simple_main_backup.py`, `backend/test_server.py`

4) Startup script updates
- Updated `external/THEIA-Job-Seekers/start_full_system.sh` to:
  - Use shared venv: `/Users/fernandoponce/interviewAnalyzer/.venv`
  - Install backend requirements into that venv if needed
  - Open SPA root (`http://localhost:3000`) instead of removed `home.html`

---

### Frontend (external/THEIA-Job-Seekers/frontend/theia-frontend)

1) API base resolution refactor
- Added `src/services/apiBase.ts` to centralize API base detection (URL param > localStorage > api-base.txt > fallback).
- Updated `src/services/theiaService.ts` and `src/services/skillsService.ts` to use the shared util.
- Removed deprecated WebSocket method from `theiaService` (backend WS removed).

2) Cleanup of unused React bits
- Removed `src/components/MySkills.tsx` (unused), `src/App.test.tsx`, `src/setupTests.ts`.

3) Deployment script simplification
- `post-build.js` now validates only `index.html` and essential assets/dirs.

4) Static routes restoration (for demo/marketing flows)
- Restored legacy static pages in `public/`:
  - `home.html` (new burger menu with links)
  - `interview.html`
  - `my-skills.html`
  - `resume.html`
  - `job-finder.html`
  - `jobs-api-base.txt` (defaults to `http://localhost:8002`)

5) Burger menu / navigation
- Added a simple burger menu to `public/home.html` linking to:
  - Mock/Prep Interview (`interview.html`)
  - Resume Builder (`resume.html`)
  - My Skills (`my-skills.html`)
  - Job Finder (`job-finder.html`)

6) Notes on auth behavior
- Some pages (e.g., `resume.html`) include an authentication guard and will redirect unauthenticated users. This is expected.

---

### Current Routes / Entry Points

- Backend API (local): `http://localhost:8000`
  - Health/credentials: `/health`, `/test/credentials`
  - Interviews: `/api/v1/interviews/*`
  - Voice: `/api/v1/voice/*`
  - Skills: `/api/v1/skills`

- Frontend (dev server): `http://localhost:3000`
  - SPA root: `/`
  - Static pages: `/home.html`, `/interview.html`, `/my-skills.html`, `/resume.html`, `/job-finder.html`

- Jobs API (Interview Analyzer, if present): `http://localhost:8002`
  - Used by `job-finder.html` (config via `public/jobs-api-base.txt`)

---

### Files Changed (high-level)

- Backend
  - Edited: `backend/simple_main.py` (merged skills logic)
  - Deleted: `backend/api/**`, `backend/main_backup.py`, `backend/websocket/**`, `backend/utils/memory.py`, `backend/simple_main_backup.py`, `backend/test_server.py`
  - Edited: `external/THEIA-Job-Seekers/start_full_system.sh` (shared venv, new open URL)

- Frontend
  - Added: `src/services/apiBase.ts`
  - Edited: `src/services/theiaService.ts`, `src/services/skillsService.ts`, `post-build.js`
  - Deleted: `src/components/MySkills.tsx`, `src/App.test.tsx`, `src/setupTests.ts`
  - Restored/Added: `public/home.html`, `public/interview.html`, `public/my-skills.html`, `public/resume.html`, `public/job-finder.html`, `public/jobs-api-base.txt`

---

### Operational Notes

1) Start everything
```
bash external/THEIA-Job-Seekers/start_full_system.sh
```
Uses venv at `/Users/fernandoponce/interviewAnalyzer/.venv`.

2) Frontend access
- SPA: `http://localhost:3000`
- Static pages: `http://localhost:3000/home.html` (menu links to all restored pages)

3) Resume Builder link behavior
- If redirected to `landing.html`, you are likely unauthenticated; log in or remove the guard if needed.

---

### Follow-ups / Options

- If desired, re-introduce React Router and migrate the static pages into SPA routes for a unified UI.
- Keep `post-build.js` minimal or enhance with SPA-specific checks.
- If websockets are needed later, add a minimal WS endpoint in `simple_main.py` and corresponding client logic.




