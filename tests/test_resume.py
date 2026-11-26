import asyncio

import pytest

from sidekick import Sidekick


@pytest.mark.parametrize("approve", [True, False])
def test_resume_sends_one_decision_per_pending_action(monkeypatch, approve):
    sidekick = Sidekick()
    sidekick.pending_actions = 2
    sent = {}

    async def fake_advance(payload, history):
        sent["payload"] = payload
        return history

    monkeypatch.setattr(sidekick, "_advance", fake_advance)
    asyncio.run(sidekick.resume([], approve=approve))
    decision = {"type": "approve" if approve else "reject"}
    assert sent["payload"].resume == {"decisions": [decision, decision]}
