# Sidekick full-stack: FastAPI backend + React frontend (design)

Approved by Aadi on 2026-11-27.

## Why
The PayPal SWE intern resume should show full-stack work on a second, AI-focused project, solid and tested, something Aadi can explain in an interview.

## Goals
- Replace the Gradio UI with a FastAPI backend wrapping the existing `Sidekick` class (no agent rewrite) and a React + TypeScript (Vite) frontend.
- Agent turns run as background jobs; the browser follows progress over Server-Sent Events.
- Human-in-the-loop approve **and deny** through the API.
- Knowledge base: list, upload (PDF/MD/TXT), re-index.
- API tests with a fake agent (no LLM, browser or network), Vitest for frontend logic, CI frontend job.

## Non-goals
Deployment, auth, multi-user, Docker. The agent drives a real browser on Aadi's machine; it stays local and single-user.

## Approaches
- **Chosen: the background job polls `sidekick.todos` every 0.5 s and broadcasts changes over SSE.** It does the same job as Gradio's 1-second timer and leaves the agent untouched.
- Rejected: add a progress callback inside `Sidekick._work`. It pushes changes sooner but changes agent code for no visible gain.
- Rejected: WebSockets. Traffic is one-way server to browser (commands go over plain POSTs), so SSE is simpler and reconnects on its own.

## Design
- **Agent change (approved):** `Sidekick.resume(history, approve=True)` sends `{"type": "approve"}` or `{"type": "reject"}` decisions.
- **`backend/api.py`:** one global session.
  - `POST /api/session` starts or resets the session (cleans up the old one, runs `setup()` in the background, about 30 s).
  - `POST /api/tasks {message, success_criteria}` starts a turn. It returns 409 when the session is busy or not ready, and 422 on an empty message.
  - `POST /api/approve {approve: bool}` resumes a paused turn. It returns 409 if nothing is paused.
  - `GET /api/state` returns the full current state.
  - `GET /api/stream` is SSE. Each event is a full state snapshot `{status, plan, messages, paused, error}`, sent on change. `status` is one of `starting | ready | running | paused | error`.
  - `GET /api/kb` lists files, `POST /api/kb` (multipart) uploads them, keeping only the file name and allowed suffixes, and `POST /api/kb/reindex` returns the chunk count.
  - `mount_frontend()` serves `frontend/dist`.
- **Frontend:** Trading Floor's Vite proxy (`API_URL`) and EventSource hook. It has a chat with markdown answers and a citations list, a live plan checklist, the task and success-criteria form, an approve/deny banner when paused, a KB upload panel and a Reset button. The visual design is clean and keeps the existing brand palette (navy, blue, gold, purple).
- **Tests:** `tests/conftest.py` swaps `Sidekick` for `FakeSidekick` and forces placeholder keys. Vitest covers the pure helpers (citation parsing, message classification).

## Left to the builder
Component layout, CSS, exact SSE framing, and how `dev` is launched (`.claude/launch.json`).
