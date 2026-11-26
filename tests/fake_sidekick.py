"""A stand-in for Sidekick with the same public surface, so API tests never start an LLM, MCP servers or a browser.

The message text picks the behaviour: "notify" pauses for approval, "boom" raises, "slow" takes 10 s.
"""

import asyncio


class FakeSidekick:
    setup_delay = 0.0
    instances: list["FakeSidekick"] = []

    def __init__(self):
        self.todos = []
        self.paused = False
        self.cleaned = False
        FakeSidekick.instances.append(self)

    async def setup(self):
        await asyncio.sleep(self.setup_delay)

    async def run_turn(self, message: str, success_criteria: str, history: list) -> list:
        self.todos = [
            {"content": "Read the task", "status": "completed"},
            {"content": "Answer it", "status": "in_progress"},
        ]
        history = history + [{"role": "user", "content": message}]
        if "boom" in message:
            raise RuntimeError("boom")
        if "slow" in message:
            await asyncio.sleep(10)
        if "notify" in message:
            self.paused = True
            return history + [{"role": "assistant", "content": "Waiting for your approval:\nsend_push_notification"}]
        return history + [{"role": "assistant", "content": f"Done: {message}"}]

    async def resume(self, history: list, approve: bool = True) -> list:
        self.paused = False
        return history + [{"role": "assistant", "content": "approved" if approve else "denied"}]

    def cleanup(self):
        self.cleaned = True
