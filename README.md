# Sidekick

A personal co-worker agent. A `create_agent` worker (browser, sandboxed filesystem, web search,
Wikipedia, push notifications) is wrapped in an evaluator loop that checks each answer against
your success criteria and retries up to 3 times. Middleware adds a shared plan, PII redaction,
a model-call limit, and human approval before sensitive actions. The UI is Gradio.

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node.js (the browser and filesystem
tools run as MCP servers via `npx`).

```
cp .env.example .env   # then fill in your keys
uv run app.py
```

## Files

- `app.py` - Gradio UI
- `sidekick.py` - worker, evaluator loop, middleware
- `sidekick_tools.py` - MCP sessions (Playwright, filesystem) and custom tools
- `styles.py` - theme, CSS and JS

The agent's working files are written to `sandbox/` (git-ignored).
