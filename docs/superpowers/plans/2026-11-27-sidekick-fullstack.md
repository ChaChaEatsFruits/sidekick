# Sidekick Full-Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Sidekick's Gradio UI with a FastAPI backend (background runs, SSE progress, approve/deny, KB upload and re-index) and a React + TypeScript frontend, tested and in CI.

**Architecture:** `api.py` at the repo root (the repo is flat: `sidekick.py`, `knowledge_base.py` live at the root, so the design's `backend/api.py` becomes `api.py`; builder's call). One module-level `Session` holds the `Sidekick`, chat history, status and the running `asyncio.Task`. `GET /api/stream` checks the session snapshot every 0.5 s and sends it whenever its JSON changes. `frontend/` is a Vite React app built on Trading Floor's proxy and EventSource patterns.

**Tech Stack:** FastAPI, uvicorn, python-multipart, pytest + httpx TestClient; React 18, TypeScript, Vite 5, Vitest 2, react-markdown.

**Spec:** `docs/superpowers/specs/2026-11-27-sidekick-fullstack-design.md`

## Global Constraints
- Do not rewrite the agent. The only change to `sidekick.py` is `resume(history, approve=True)`.
- Tests never call a real LLM, browser, Serper, Pushover or the real `kb/` and `chroma_db/`. conftest forces placeholder keys even when `.env` has real ones (`load_dotenv(override=True)`).
- Local, single user, no auth, no Docker.
- KB uploads allow only `.pdf`, `.md`, `.txt` and keep only `Path(name).name`.
- CI: the existing `test` job (uv sync --frozen, ruff 0.14.0, pytest) plus a `frontend` job (npm ci, npm test, npm run build) on Node 22.
- Each milestone (end of Task 2, end of Task 4) is pushed to `main` and CI goes green before moving on. Check with `gh run list --commit <full sha>`.

## Review Focus
- Reset while a turn is running → the running task is cancelled, the old sidekick cleaned up, and the new session starts. Pinned in Task 2 `test_reset_cancels_running_turn`.
- A task sent while the session is still starting (setup about 30 s) → 409 and no crash. Pinned in Task 2 `test_task_rejected_while_starting`.
- The agent raises mid-turn → status `error` with the message, and the next task is accepted. Pinned in Task 2 `test_agent_error_reported_and_recoverable`.
- Upload named `../../evil.md` or `x.exe` → stored as `kb/evil.md` / rejected with 422. Pinned in Task 2 `test_upload_sanitises_and_filters`.
- SSE reconnect after a backend restart → EventSource reconnects by itself and the first event is a full snapshot (each event is a full snapshot, so nothing is lost). Covered by design, no test.

---

### Task 1: Deny support in the agent

**Files:**
- Modify: `sidekick.py` (`resume`)
- Test: `tests/test_resume.py`

**Interfaces:**
- Produces: `async Sidekick.resume(history: list, approve: bool = True) -> list`

- [ ] **Step 1: Write the failing test** `test_resume_sends_one_decision_per_pending_action(approve)`, parametrized over True/False. Build `Sidekick()` without `setup()`, set `pending_actions = 2`, monkeypatch `_advance` with an async stub that captures `payload`. Assert `payload.resume == {"decisions": [{"type": "approve" if approve else "reject"}] * 2}`.
- [ ] **Step 2: Run** `uv run pytest tests/test_resume.py -v`. Expected: FAIL (unexpected keyword `approve`).
- [ ] **Step 3: Implement.** Add the `approve` parameter and pick the decision type from it. Update the docstring to "Approve or reject the actions the worker paused on".
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: let resume() reject paused actions`

### Task 2: FastAPI backend with fake-agent tests (milestone 1)

**Files:**
- Create: `api.py`, `tests/conftest.py`, `tests/fake_sidekick.py`, `tests/test_api.py`
- Modify: `pyproject.toml`, `uv.lock` (`uv add fastapi uvicorn python-multipart`, `uv add --dev httpx`), `.claude/launch.json` (add `api`: `uv run uvicorn api:app --port 8000`; pick another port if 8000 is taken)

**Interfaces:**
- Consumes: Task 1 `resume(history, approve)`. `Sidekick.setup/run_turn/todos/paused/cleanup` as they are today. `knowledge_base.KB_DIR`, `knowledge_base.build_index() -> int`.
- Produces (the HTTP contract Task 3 uses):
  - `Snapshot = {status: "starting"|"ready"|"running"|"paused"|"error", plan: [{content, status}], messages: [{role, content}], error: str|None}`
  - `POST /api/session` → 202 `Snapshot` (reset)
  - `POST /api/tasks {message: str (min 1 after strip), success_criteria: str = ""}` → 202 / 409 / 422
  - `POST /api/approve {approve: bool}` → 202 / 409
  - `GET /api/state` → `Snapshot`
  - `GET /api/stream` → `text/event-stream`, `data: <Snapshot JSON>\n\n`
  - `GET /api/kb` → `{files: [str]}`; `POST /api/kb` multipart `files` → `{files: [str]}` / 422; `POST /api/kb/reindex` → `{chunks: int, files: [str]}`
  - `api.snapshot_events(interval: float = 0.5)` async generator of SSE strings
  - `api.mount_frontend(app, dist: Path) -> bool` (copied from Trading Floor)

Behaviour:
- `lifespan` starts a session at startup and calls `cleanup()` at shutdown.
- `start_session()` cancels any running task, cleans up the old sidekick, creates `Sidekick()`, sets status `starting`, and runs `setup()` as an `asyncio.Task`. When setup finishes the status becomes `ready`; if it fails, `error` with `ready=False`.
- A turn runs `run_turn(...)` or `resume(...)` as an `asyncio.Task`. Afterwards status is `paused` if `sidekick.paused`, else `ready`. An exception gives `error` with `str(exc)`, while `ready` stays True so the next task is allowed.
- `/api/tasks` is accepted only when the session is ready and the status is `ready` or `error`. `/api/approve` is accepted only when the status is `paused`. On a 409 the `detail` says why.

conftest (autouse, before importing `api`): set `OPENAI_API_KEY`/`SERPER_API_KEY` placeholders, import `api`, re-set the placeholders with monkeypatch after the import's `load_dotenv(override=True)`, monkeypatch `api.Sidekick = FakeSidekick`, and monkeypatch `knowledge_base.KB_DIR` to `tmp_path` and `knowledge_base.build_index` to count the files. Yields a `client` fixture: `with TestClient(api.app) as c`. Add a `wait_for(client, status)` helper that polls `/api/state` for up to 2 s.

`FakeSidekick`: async `setup()` sleeps `FakeSidekick.setup_delay` seconds (class attribute, default 0, reset by conftest). `run_turn` sets `todos` to two items, appends the user message and `"Done: <message>"`. A message containing `"notify"` sets `paused=True` and appends `"Waiting for your approval:\nsend_push_notification"`. A message containing `"boom"` raises `RuntimeError("boom")`. A message containing `"slow"` sleeps 10 s. `resume(history, approve)` clears `paused` and appends `"approved"` or `"denied"`. `cleanup()` sets `cleaned = True`.

- [ ] **Step 1: Write failing tests** in `tests/test_api.py`:
  - `test_session_starts_ready`: `wait_for("ready")`, then `messages == []`.
  - `test_task_runs_in_background_and_finishes`: POST a task → 202, `wait_for("ready")`, last message `"Done: hi"`, plan has 2 items.
  - `test_empty_message_rejected`: `"   "` → 422.
  - `test_task_rejected_while_running`: a `"slow"` task, then a second → 409.
  - `test_task_rejected_while_starting`: `FakeSidekick.setup_delay = 5`, reset, task → 409.
  - `test_pause_then_approve` / `test_pause_then_deny`: a `"notify"` task → `wait_for("paused")`, approve with True/False → `wait_for("ready")`, last message `"approved"`/`"denied"`.
  - `test_approve_when_not_paused_is_409`.
  - `test_agent_error_reported_and_recoverable`: a `"boom"` task → `wait_for("error")`, `error == "boom"`, then `"hi"` → 202.
  - `test_reset_cancels_running_turn`: a `"slow"` task, reset → status `starting`/`ready`, old fake `cleaned`, `messages == []`.
  - `test_stream_first_event_is_snapshot`: `anext(api.snapshot_events())` starts with `"data: "` and its JSON has a `status` key (use `asyncio.run` on a small coroutine).
  - `test_kb_list_upload_reindex`: upload `a.md`, list contains it, reindex → `chunks == 1`.
  - `test_upload_sanitises_and_filters`: `../../evil.md` → saved as `tmp_path/"evil.md"`, `x.exe` → 422 and nothing is saved.
  - `test_mount_frontend` (true with a dist that has an index.html, false without one).
- [ ] **Step 2: Run** `uv run pytest tests/test_api.py -v`. Expected: FAIL (no module `api`).
- [ ] **Step 3: Implement `api.py`** to the contract above. The SSE response uses `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control": "no-cache"})` like Trading Floor's.
- [ ] **Step 4: Run** `uv run pytest -q` and `uvx ruff@0.14.0 check .`. Expected: all pass, including the 4 existing KB tests.
- [ ] **Step 5: Smoke-test by hand.** `uv run uvicorn api:app --port 8000`, then `curl /api/state` until `ready`.
- [ ] **Step 6: Commit and push** `feat: FastAPI backend with background runs, SSE and approve/deny`, then confirm CI is green.

### Task 3: React frontend with Vitest

**Files:**
- Create: `frontend/{package.json,tsconfig.json,vite.config.ts,index.html}` (copied from Trading Floor and renamed; deps `react`, `react-dom`, `react-markdown`), `frontend/src/{main.tsx,App.tsx,api.ts,styles.css}`, `frontend/src/hooks/useSession.ts`, `frontend/src/lib/messages.ts`, `frontend/src/lib/messages.test.ts`, `frontend/src/components/{Chat,PlanPanel,TaskForm,ApprovalBanner,KnowledgeBase}.tsx`
- Modify: `.claude/launch.json` (add `web`: `npm --prefix frontend run dev`, port 5173), `.gitignore` (`frontend/node_modules`, `frontend/dist`)

**Interfaces:**
- Consumes: the Task 2 HTTP contract.
- Produces:
  - `lib/messages.ts`: `type Kind = "user"|"answer"|"sources"|"evaluator"|"metrics"|"approval"`; `classify(m: {role, content}) -> Kind` (by role, then by prefix: `"Sources:\n"`, `"Evaluator: "`, `"Metrics: "`, `"Waiting for your approval:"`); `parseSources(content) -> {id: string, snippet: string, missing: boolean}[]` (lines like `- **pep8.md#11**: text…`; `missing` when the text starts with `⚠`).
  - `api.ts`: `Snapshot` type, plus `startTask`, `approve(bool)`, `reset`, `listKb`, `uploadKb(FileList)`, `reindexKb`. Each throws an `Error` carrying the `detail` text on a non-2xx response.
  - `useSession(): Snapshot | null` (EventSource on `/api/stream`, like `useLiveSnapshot`).

UI: header with the Sidekick brand bar. Chat on the left: user bubbles; answers rendered with react-markdown; sources as a citation list (missing ones flagged); evaluator and metrics as small muted lines. Plan checklist on the right, with pending/in_progress/completed marks. Below: message and success-criteria inputs plus a Go button, disabled unless the status is `ready`/`error`. A gold approve/deny banner shows while `paused`. A status pill shows starting/running. A collapsible KB panel has upload, a file list and Re-index. Reset sits in the header. API errors show inline. Keep the palette from `styles.py` (navy `#032147`, blue `#209DD7`, gold `#FFB706`, purple `#753991`, bg `#F2F2F2`).

- [ ] **Step 1: Write failing tests** in `messages.test.ts`: classify each of the 6 kinds; `parseSources` on a two-line sample with one `⚠ not in the knowledge base` entry → 2 items, the second has `missing: true`; non-source text → `[]`.
- [ ] **Step 2: Run** `npm --prefix frontend test`. Expected: FAIL.
- [ ] **Step 3: Implement** `lib/messages.ts`, then the rest of the app.
- [ ] **Step 4: Run** `npm --prefix frontend test` and `npm --prefix frontend run build`. Expected: pass, no type errors.
- [ ] **Step 5: Check by hand** with the real backend and the Vite dev server in the Browser pane: send a task, watch the plan tick, approve a push notification, upload a KB file and re-index.
- [ ] **Step 6: Commit** `feat: React + TypeScript frontend`

### Task 4: Remove Gradio, CI frontend job, docs (milestone 2)

**Files:**
- Delete: `app.py`, `styles.py`
- Modify: `pyproject.toml`/`uv.lock` (`uv remove gradio`; update the description), `.github/workflows/ci.yml` (add the `frontend` job copied from Trading Floor), `README.md` (run instructions: `uv run uvicorn api:app`, `npm --prefix frontend run dev`, or build once and open :8000; update the file list), `.claude/launch.json` (drop the gradio entry), test comment in `tests/test_knowledge_base.py` ("Gradio re-index button" → "re-index endpoint")

- [ ] **Step 1:** `grep -ri gradio` across tracked files returns nothing except the lockfile history.
- [ ] **Step 2: Run** `uv sync`, `uv run pytest -q`, `uvx ruff@0.14.0 check .`, `npm --prefix frontend test`, `npm --prefix frontend run build`. Expected: all pass.
- [ ] **Step 3: Check** that `uv run uvicorn api:app` serves the built app at `/` (`id="root"`).
- [ ] **Step 4: Commit and push** `chore: remove Gradio; CI frontend job; README`, then confirm both CI jobs are green.

### Task 5: Resume and brain note

**Files:**
- Backup: `Desktop\CSE\resume\bak_resume\aadinarayan_r_resume_paypal_<date>.tex`
- Modify: `Desktop\CSE\resume\aadinarayan_r_resume_paypal.tex` (Sidekick entry), `brain\areas\career\resume-versions.md`

- [ ] **Step 1:** Back up the .tex. Rewrite the Sidekick entry: tools line `Python, LangGraph, MCP, FastAPI, React, TypeScript, Chroma`, plus 2 bullets that claim only what has been pushed: the agent and RAG metric, and the FastAPI/SSE/HITL/React/tests/CI.
- [ ] **Step 2:** Compile with tectonic. Confirm 1 page, then render and look for bullets that wrap by only a word or two.
- [ ] **Step 3:** Update `resume-versions.md` through the zettel house format.
