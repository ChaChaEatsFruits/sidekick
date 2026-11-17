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
uv run app.py
```

## Files

- `app.py` - Gradio UI
- `sidekick.py` - worker, evaluator loop, middleware
- `sidekick_tools.py` - MCP sessions (Playwright, filesystem) and custom tools
- `styles.py` - theme, CSS and JS
- `knowledge_base.py` - load, chunk, embed, store and search the documents in `kb/`

The agent's working files are written to `sandbox/` (git-ignored).
