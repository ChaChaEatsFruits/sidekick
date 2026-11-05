# Sidekick

A personal co-worker agent. A LangChain `create_agent` worker is wrapped in an evaluator loop that
checks each answer against your success criteria and retries up to 3 times, or returns to you with
a question. The UI is Gradio.

## How it works

- **Worker** (`openai:gpt-5.4-mini`) with tools: a headed browser (Playwright MCP), a sandboxed
  filesystem (filesystem MCP), web search (Serper), Wikipedia, push notifications, and
  `request_human_help` for logins, captchas and two-factor prompts.
- **Evaluator** (`gpt-5.4-mini`, structured output) judges each reply against your success
  criteria, using the list of tools the worker actually called as evidence.
- **Middleware**: a shared to-do plan, email and credit-card PII redaction, a 30-call model limit,
  tool errors handed back to the model so it can recover, and human approval before
  `send_push_notification` and `request_human_help`.

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node.js (the browser and filesystem
tools run as MCP servers via `npx`).

```
cp .env.example .env   # OPENAI_API_KEY, SERPER_API_KEY; optional PUSHOVER_USER / PUSHOVER_TOKEN
uv run app.py
```

## Files

- `app.py` - Gradio UI
- `sidekick.py` - worker, evaluator loop, middleware
- `sidekick_tools.py` - MCP sessions (Playwright, filesystem) and custom tools
- `styles.py` - theme, CSS and JS

The agent's working files are written to `sandbox/` (git-ignored).
