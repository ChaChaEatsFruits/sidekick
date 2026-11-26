"""FastAPI backend for the Sidekick. Run with: uv run uvicorn api:app --port 8000

The agent drives a real browser on this machine, so there is one session for one local user.
A turn takes minutes, so every agent call runs as a background asyncio task on the server's event
loop (the MCP browser session lives on that loop too) and the browser follows along over SSE.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

import knowledge_base
from sidekick import Sidekick

KB_TYPES = {".pdf", ".md", ".txt"}


class Session:
    """One Sidekick plus what the page shows: status, chat messages and the last error."""

    def __init__(self):
        self.sidekick = Sidekick()
        self.status = "starting"  # starting | ready | running | paused | error
        self.ready = False  # setup() finished; an "error" after setup still accepts new tasks
        self.messages: list[dict] = []
        self.error: str | None = None
        self.job: asyncio.Task | None = None

    def snapshot(self) -> dict:
        return {"status": self.status, "plan": self.sidekick.todos, "messages": self.messages, "error": self.error}

    def stop(self):
        if self.job:
            self.job.cancel()
        self.sidekick.cleanup()


session: Session | None = None


async def _setup(s: Session):
    try:
        await s.sidekick.setup()
        s.ready, s.status = True, "ready"
    except Exception as exc:
        s.status, s.error = "error", f"Sidekick failed to start: {exc}. Press Reset to try again."


async def _run(s: Session, work):
    """Await an agent call (run_turn or resume) and record where it left the session."""
    try:
        s.messages = await work
        s.status = "paused" if s.sidekick.paused else "ready"
    except Exception as exc:  # CancelledError is not an Exception, so a reset still cancels cleanly
        s.status, s.error = "error", str(exc) or type(exc).__name__


def start_session() -> Session:
    """Throw away the current session (cancelling any running turn, closing its browser) and start a new one."""
    global session
    if session:
        session.stop()
    session = Session()
    session.job = asyncio.create_task(_setup(session))
    return session


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_session()
    yield
    session.stop()


app = FastAPI(title="Sidekick", lifespan=lifespan)


class TaskIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    success_criteria: str = ""


class ApproveIn(BaseModel):
    approve: bool


@app.get("/api/state")
def get_state() -> dict:
    return session.snapshot()


@app.post("/api/session", status_code=202)
async def reset() -> dict:
    return start_session().snapshot()


@app.post("/api/tasks", status_code=202)
async def post_task(task: TaskIn) -> dict:
    s = session
    if not s.ready:
        raise HTTPException(409, "The Sidekick is still starting" if s.status == "starting" else s.error)
    if s.status not in ("ready", "error"):
        raise HTTPException(409, f"The Sidekick is {s.status}; wait for it to finish")
    history = s.messages
    # show the user's message straight away; run_turn adds it to the history it returns
    s.messages = history + [{"role": "user", "content": task.message}]
    s.status, s.error = "running", None  # set before the task starts, so a second request sees "running"
    s.job = asyncio.create_task(_run(s, s.sidekick.run_turn(task.message, task.success_criteria, history)))
    return s.snapshot()


@app.post("/api/approve", status_code=202)
async def approve(body: ApproveIn) -> dict:
    s = session
    if s.status != "paused":
        raise HTTPException(409, "Nothing is waiting for approval")
    s.status = "running"
    s.job = asyncio.create_task(_run(s, s.sidekick.resume(s.messages, approve=body.approve)))
    return s.snapshot()


async def snapshot_events(interval: float = 0.5):
    """Send the full state whenever it changes. Checking every half second picks up the agent's plan
    (sidekick.todos), which the agent updates in place; full snapshots make reconnects lossless."""
    last = None
    while True:
        snap = json.dumps(session.snapshot())
        if snap != last:
            last = snap
            yield f"data: {snap}\n\n"
        await asyncio.sleep(interval)


@app.get("/api/stream")
def stream() -> StreamingResponse:
    return StreamingResponse(snapshot_events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def kb_files() -> list[str]:
    return sorted(p.name for p in knowledge_base.KB_DIR.iterdir() if p.suffix.lower() in KB_TYPES)


@app.get("/api/kb")
def get_kb() -> dict:
    return {"files": kb_files()}


@app.post("/api/kb")
async def upload_kb(files: list[UploadFile]) -> dict:
    names = [Path(f.filename or "").name for f in files]  # .name keeps only the file name, never a path
    if bad := [n or "(unnamed)" for n in names if Path(n).suffix.lower() not in KB_TYPES]:
        raise HTTPException(422, f"Only PDF, Markdown and text files can be added: {', '.join(bad)}")
    for upload, name in zip(files, names):
        (knowledge_base.KB_DIR / name).write_bytes(await upload.read())
    return {"files": kb_files()}


@app.post("/api/kb/reindex")
async def reindex_kb() -> dict:
    chunks = await asyncio.to_thread(knowledge_base.build_index)
    return {"chunks": chunks, "files": kb_files()}


def mount_frontend(target: FastAPI, dist: Path) -> bool:
    """Serve the built React app at /, mounted after every /api route so the API always wins.
    In development the Vite server serves the frontend instead and dist/ may not exist."""
    if not (dist / "index.html").is_file():
        return False
    target.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


mount_frontend(app, Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parent / "frontend" / "dist")))
