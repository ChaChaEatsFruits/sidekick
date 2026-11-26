# Sidekick

[![CI](https://github.com/ChaChaEatsFruits/sidekick/actions/workflows/ci.yml/badge.svg)](https://github.com/ChaChaEatsFruits/sidekick/actions/workflows/ci.yml)

A personal co-worker agent. A LangChain `create_agent` worker is wrapped in an evaluator loop that
checks each answer against your success criteria and retries up to 3 times, or returns to you with
a question. It runs locally as a FastAPI backend and a React + TypeScript frontend.

## How it works

- **Worker** (`openai:gpt-5.4-mini`) with tools: a headed browser (Playwright MCP), a sandboxed
  filesystem (filesystem MCP), web search (Serper), Wikipedia, push notifications, and
  `request_human_help` for logins, captchas and two-factor prompts.
- **Evaluator** (`gpt-5.4-mini`, structured output) judges each reply against your success
  criteria, using the list of tools the worker actually called as evidence.
- **Middleware**: a shared to-do plan, email and credit-card PII redaction, a 30-call model limit,
  tool errors handed back to the model so it can recover, and human approval before
  `send_push_notification` and `request_human_help`.

## Web app

A turn can take minutes, so the API never makes the browser wait for one:

- `POST /api/tasks` starts the turn as a background asyncio task and returns `202` straight away;
  a second task while one is running gets `409`.
- `GET /api/stream` is a Server-Sent Events stream. Whenever the session changes (status, chat,
  the agent's live plan), it sends the whole state, so a dropped connection catches up on reconnect.
- When the agent pauses before a sensitive tool, the page shows an approve/deny banner;
  `POST /api/approve {"approve": true|false}` resumes the LangGraph interrupt with that decision.
- `POST /api/session` resets: it cancels any running turn and closes the agent's browser.
- `GET/POST /api/kb` and `POST /api/kb/reindex` list, upload and re-index the knowledge base.

It is single-user and local on purpose: the agent drives a real browser window on your machine.

The API tests swap the agent for a fake (`tests/fake_sidekick.py`), so they never call OpenAI,
a browser or the network. The frontend has Vitest tests, and CI runs both.

## Knowledge base (RAG)

Drop PDF, Markdown or text files into `kb/` (or upload them in the UI's Knowledge base panel) and
click **Add and re-index**. The agent's `search_knowledge_base` tool retrieves the top chunks and
answers with `[file#chunk]` citations, which the chat expands into a Sources list.

- Chunks of 800 characters with 120 overlap, embedded locally with `all-MiniLM-L6-v2`, stored in Chroma (`chroma_db/`)
- Chunks below 0.3 cosine similarity are dropped, so the agent says when the knowledge base has no answer
- Each finished turn shows tokens, estimated cost, tokens/sec and retrieval latency, and logs them to `metrics.jsonl`

Evaluation on a 20-question golden set (`eval/`, results in `eval/results.md`):

```
uv run python -m eval.eval_retrieval      # hit rate@k and MRR for 3 chunk sizes, local, free
uv run python -m eval.eval_faithfulness   # LLM-judged faithfulness, ~40 gpt-5.4-mini calls
uv run pytest
```

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node.js (the browser and filesystem
tools run as MCP servers via `npx`).

```
cp .env.example .env   # OPENAI_API_KEY, SERPER_API_KEY; optional PUSHOVER_USER / PUSHOVER_TOKEN
npm --prefix frontend ci
npm --prefix frontend run build
uv run uvicorn api:app --port 8000   # then open http://127.0.0.1:8000
```

For frontend development, run `npm --prefix frontend run dev` alongside the API and open
http://localhost:5173; Vite proxies `/api` to port 8000 (set `API_URL` to use another port).

Tests: `uv run pytest` and `npm --prefix frontend test`.

## Files

- `api.py` - FastAPI backend: session, background turns, SSE stream, approvals, knowledge base
- `frontend/` - React + TypeScript (Vite) app
- `sidekick.py` - worker, evaluator loop, middleware
- `sidekick_tools.py` - MCP sessions (Playwright, filesystem) and custom tools
- `knowledge_base.py` - load, chunk, embed, store and search the documents in `kb/`

The agent's working files are written to `sandbox/` (git-ignored).
