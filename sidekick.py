"""The Sidekick: a create_agent worker wrapped in a homemade evaluator loop.

The worker is a single create_agent (Layer 3). Around it we run our own loop that checks
the worker's answer against the user's success criteria, and either accepts it, sends it
back for another attempt, or returns to the user with a question. Middleware gives the
worker a plan it shares with the UI, guardrails for PII and runaway costs, and a pause
for human approval before sensitive actions.
"""

import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    TodoListMiddleware,
)
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import knowledge_base
from sidekick_tools import get_all_tools

load_dotenv(override=True)

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(HERE, "sandbox")
MAX_ATTEMPTS = 3
PRICE_PER_MILLION = {"input": 0.75, "output": 4.50}  # gpt-5.4-mini list price, Nov 2026; ignores cache discounts
METRICS_LOG = os.path.join(HERE, "metrics.jsonl")


class EvaluatorOutput(BaseModel):
    feedback: str = Field(description="Feedback on the assistant's response")
    success_criteria_met: bool = Field(description="Whether the success criteria have been met")
    user_input_needed: bool = Field(
        description="True if the assistant has a question, needs clarification, or is stuck and needs the user"
    )


WORKER_PROMPT = """You are Sidekick, a capable personal assistant who completes tasks for the user.
You have a real web browser, a sandbox filesystem, web search, Wikipedia, and the ability to send push notifications.
When you use the browser, navigate to a page and read it with a snapshot rather than clicking around unnecessarily.
Dismiss cookie banners and popups yourself by clicking in the browser. If you reach something only a human can do,
like logging in, a captcha, or two-factor authentication, use the request_human_help tool to tell the user exactly
what to do in your browser window, then carry on once they have done it.
For flight searches, use Google Flights in your browser: go straight to https://www.google.com/travel/flights?q=...
with a natural language query like "flights from New York to London leaving 14 July returning 21 July".
The user has a knowledge base of their own documents. For questions it may cover, call search_knowledge_base
first, answer only from the chunks it returns, and cite every claim with the chunk label, like [pep8.md#11].
If the knowledge base has nothing relevant, say so before using other sources.
Keep working on the task until the success criteria are met, or until you genuinely need to ask the user a question.
If you have a question, ask it plainly. When you are finished, give your final answer clearly,
saying what you did, what you produced, and what you found."""


class TolerateToolErrors(AgentMiddleware):
    """Hand tool failures back to the model as a message so it can recover, rather than
    crashing the run. Tools that touch the outside world, like a browser, fail now and then."""

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as error:
            return ToolMessage(
                content=f"That tool call failed: {error}. Try another approach.",
                tool_call_id=request.tool_call["id"],
            )


def cited_sources(reply: str) -> str | None:
    """List the [file#chunk] citations in a reply with a snippet of each, flagging any that do not exist."""
    ids = list(dict.fromkeys(re.findall(r"\[([^\[\]#\s]+#\d+)\]", reply)))
    if not ids:
        return None
    found = knowledge_base.get_chunks(ids)
    lines = [
        f"- **{i}**: {' '.join(found[i].split())[:160]}…" if i in found else f"- **{i}**: ⚠ not in the knowledge base"
        for i in ids
    ]
    return "Sources:\n" + "\n".join(lines)


class Metrics(AgentMiddleware):
    """Times the worker's model calls (for tokens/sec) and knowledge-base retrievals, per turn."""

    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self):
        self.model_seconds = 0.0
        self.model_output_tokens = 0
        self.retrieval_ms = []

    async def awrap_model_call(self, request, handler):
        start = time.perf_counter()
        response = await handler(request)
        self.model_seconds += time.perf_counter() - start
        self.model_output_tokens += sum((getattr(m, "usage_metadata", None) or {}).get("output_tokens", 0)
                                        for m in response.result)
        return response

    async def awrap_tool_call(self, request, handler):
        start = time.perf_counter()
        result = await handler(request)
        if request.tool_call["name"] == "search_knowledge_base":
            self.retrieval_ms.append(round((time.perf_counter() - start) * 1000, 1))
        return result


class Sidekick:
    def __init__(self):
        self.sidekick_id = str(uuid.uuid4())
        self.memory = InMemorySaver()
        self.tools = None
        self.sessions = None
        self.worker = None
        self.evaluator = None
        self.task = ""
        self.success_criteria = ""
        self.attempts = 0
        self.paused = False
        self.pending_actions = 0
        self.todos = []
        self.metrics = Metrics()
        self.tokens = {"input": 0, "output": 0}
        self.turn_seconds = 0.0

    async def setup(self):
        os.makedirs(SANDBOX, exist_ok=True)
        await asyncio.to_thread(knowledge_base.warm_up)
        self.tools, self.sessions = await get_all_tools(SANDBOX)
        self.worker = create_agent(
            model="openai:gpt-5.4-mini",
            tools=self.tools,
            system_prompt=f"{WORKER_PROMPT}\nToday is {datetime.now():%A %d %B %Y}.",
            middleware=[
                TolerateToolErrors(),
                self.metrics,
                TodoListMiddleware(),
                PIIMiddleware("email"),
                PIIMiddleware("credit_card", apply_to_tool_results=True),
                ModelCallLimitMiddleware(run_limit=30),
                HumanInTheLoopMiddleware(
                    interrupt_on={"send_push_notification": True, "request_human_help": True}
                ),
            ],
            checkpointer=self.memory,
        )
        self.evaluator = ChatOpenAI(model="gpt-5.4-mini").with_structured_output(EvaluatorOutput)

    async def evaluate(
        self, message: str, success_criteria: str, last_reply: str, tools_used: list[str]
    ) -> EvaluatorOutput:
        prompt = f"""You decide whether an assistant has met the success criteria for a task.

The user's request was:
{message}

The success criteria are:
{success_criteria}

The tools the assistant called while working, in order:
{", ".join(tools_used) or "none"}

The assistant's most recent reply was:
{last_reply}

Decide whether the success criteria are met, using the tool calls as evidence of what was actually done.
Also decide whether the assistant needs more input from the user, either because it asked a question,
needs clarification, or seems stuck. Give brief, concrete feedback."""
        return await self.evaluator.ainvoke(prompt)

    async def run_turn(self, message: str, success_criteria: str, history: list) -> list:
        """One turn of conversation: the worker attempts the task and the evaluator checks it,
        retrying with feedback up to MAX_ATTEMPTS. If the worker pauses for approval, this
        returns straight away with paused set, and resume() continues the same turn."""
        self.task = message
        self.success_criteria = success_criteria or "The answer should be clear, correct and complete"
        self.attempts = 0
        self.todos = []
        self.metrics.reset()
        self.tokens = {"input": 0, "output": 0}
        self.turn_seconds = 0.0
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": f"{message}\n\nThe success criteria for this task are: {self.success_criteria}",
                }
            ]
        }
        return await self._advance(payload, history + [{"role": "user", "content": message}])

    async def resume(self, history: list) -> list:
        """Approve the actions the worker paused on, and continue the turn."""
        payload = Command(resume={"decisions": [{"type": "approve"}] * self.pending_actions})
        return await self._advance(payload, history)

    async def _advance(self, payload, history: list) -> list:
        """Run the worker and evaluator, counting tokens and time. Once the turn is finished
        (not paused for approval), add a metrics line to the chat and log it."""
        start = time.perf_counter()
        with get_usage_metadata_callback() as usage:  # sees every model call: worker and evaluator
            history = await self._work(payload, history)
        self.turn_seconds += time.perf_counter() - start
        for model_usage in usage.usage_metadata.values():
            self.tokens["input"] += model_usage["input_tokens"]
            self.tokens["output"] += model_usage["output_tokens"]
        if self.paused:
            return history
        return history + [{"role": "assistant", "content": self._report_metrics()}]

    def _report_metrics(self) -> str:
        m = self.metrics
        cost = sum(self.tokens[kind] * PRICE_PER_MILLION[kind] for kind in self.tokens) / 1e6
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "task": self.task[:80],
            "attempts": self.attempts,
            "input_tokens": self.tokens["input"],
            "output_tokens": self.tokens["output"],
            "cost_usd": round(cost, 5),
            "turn_seconds": round(self.turn_seconds, 1),
            "worker_tokens_per_sec": round(m.model_output_tokens / m.model_seconds, 1) if m.model_seconds else None,
            "retrieval_ms": m.retrieval_ms,
        }
        with open(METRICS_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
        retrieval = f", retrieval {', '.join(f'{ms:g} ms' for ms in m.retrieval_ms)}" if m.retrieval_ms else ""
        return (f"Metrics: {record['input_tokens']:,} in / {record['output_tokens']:,} out tokens, "
                f"~${cost:.4f}, {record['turn_seconds']}s, {record['worker_tokens_per_sec']} tok/s{retrieval}")

    async def _work(self, payload, history: list) -> list:
        config ={"configurable": {"thread_id": self.sidekick_id}}
        while True:
            result = None
            async for result in self.worker.astream(payload, config=config, stream_mode="values"):
                self.todos = result.get("todos", self.todos)

            if "__interrupt__" in result:
                actions = result["__interrupt__"][0].value["action_requests"]
                self.paused = True
                self.pending_actions = len(actions)
                described = "\n".join(action["description"] for action in actions)
                return history + [{"role": "assistant", "content": f"Waiting for your approval:\n{described}"}]

            self.paused = False
            reply = result["messages"][-1].content
            tools_used = [
                call["name"] for m in result["messages"] for call in (getattr(m, "tool_calls", None) or [])
            ]
            self.attempts += 1
            verdict = await self.evaluate(self.task, self.success_criteria, reply, tools_used)
            if verdict.success_criteria_met or verdict.user_input_needed or self.attempts >= MAX_ATTEMPTS:
                return history + [
                    {"role": "assistant", "content": reply},
                    *([{"role": "assistant", "content": sources}] if (sources := cited_sources(reply)) else []),
                    {"role": "assistant", "content": f"Evaluator: {verdict.feedback}"},
                ]
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Your last response did not meet the success criteria. "
                        f"Here is the feedback: {verdict.feedback}. Please keep working and address it.",
                    }
                ]
            }

    def cleanup(self):
        """Shut down the MCP servers; the browser window closes."""
        if self.sessions:
            self.sessions.stop()
