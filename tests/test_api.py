import asyncio
import json
import time

import api
from tests.fake_sidekick import FakeSidekick


def wait_for(client, status: str, timeout: float = 2.0) -> dict:
    """Poll the state until the background job reaches `status`; the agent runs off the request."""
    deadline = time.monotonic() + timeout
    while True:
        state = client.get("/api/state").json()
        if state["status"] == status or time.monotonic() > deadline:
            assert state["status"] == status, state
            return state
        time.sleep(0.02)


def send(client, message: str, criteria: str = ""):
    return client.post("/api/tasks", json={"message": message, "success_criteria": criteria})


def test_session_starts_ready(client):
    state = wait_for(client, "ready")
    assert state["messages"] == [] and state["plan"] == [] and state["error"] is None


def test_task_runs_in_background_and_finishes(client):
    wait_for(client, "ready")
    assert send(client, "hi").status_code == 202
    state = wait_for(client, "ready")
    assert state["messages"] == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Done: hi"}]
    assert len(state["plan"]) == 2


def test_empty_message_rejected(client):
    wait_for(client, "ready")
    assert send(client, "   ").status_code == 422


def test_task_rejected_while_running(client):
    wait_for(client, "ready")
    assert send(client, "slow").status_code == 202
    state = client.get("/api/state").json()
    assert state["status"] == "running"
    assert state["messages"][-1] == {"role": "user", "content": "slow"}  # shown before the agent answers
    second = send(client, "hi")
    assert second.status_code == 409 and "running" in second.json()["detail"]


def test_task_rejected_while_starting(client, monkeypatch):
    wait_for(client, "ready")
    monkeypatch.setattr(FakeSidekick, "setup_delay", 5.0)
    assert client.post("/api/session").json()["status"] == "starting"
    assert send(client, "hi").status_code == 409


def test_pause_then_approve(client):
    wait_for(client, "ready")
    send(client, "notify me")
    assert wait_for(client, "paused")["messages"][-1]["content"].startswith("Waiting for your approval")
    assert client.post("/api/approve", json={"approve": True}).status_code == 202
    assert wait_for(client, "ready")["messages"][-1]["content"] == "approved"


def test_pause_then_deny(client):
    wait_for(client, "ready")
    send(client, "notify me")
    wait_for(client, "paused")
    assert client.post("/api/approve", json={"approve": False}).status_code == 202
    assert wait_for(client, "ready")["messages"][-1]["content"] == "denied"


def test_approve_when_not_paused_is_409(client):
    wait_for(client, "ready")
    assert client.post("/api/approve", json={"approve": True}).status_code == 409


def test_agent_error_reported_and_recoverable(client):
    wait_for(client, "ready")
    send(client, "boom")
    assert wait_for(client, "error")["error"] == "boom"
    assert send(client, "hi").status_code == 202
    state = wait_for(client, "ready")
    assert state["error"] is None and state["messages"][-1]["content"] == "Done: hi"


def test_reset_cancels_running_turn(client):
    wait_for(client, "ready")
    send(client, "slow")
    old = FakeSidekick.instances[-1]
    client.post("/api/session")
    state = wait_for(client, "ready")
    assert old.cleaned and FakeSidekick.instances[-1] is not old
    assert state["messages"] == []


def test_stream_first_event_is_snapshot(client):
    wait_for(client, "ready")

    async def first_event():
        events = api.snapshot_events()
        try:
            return await anext(events)
        finally:
            await events.aclose()

    event = asyncio.run(first_event())
    assert event.startswith("data: ") and event.endswith("\n\n")
    assert json.loads(event.removeprefix("data: "))["status"] == "ready"


def test_kb_list_upload_reindex(client, kb_dir):
    assert client.get("/api/kb").json() == {"files": []}
    response = client.post("/api/kb", files=[("files", ("a.md", b"# A", "text/markdown"))])
    assert response.json() == {"files": ["a.md"]}
    assert client.post("/api/kb/reindex").json() == {"chunks": 1, "files": ["a.md"]}


def test_upload_sanitises_and_filters(client, kb_dir):
    ok = client.post("/api/kb", files=[("files", ("../../evil.md", b"x", "text/markdown"))])
    assert ok.status_code == 200 and (kb_dir / "evil.md").read_bytes() == b"x"
    bad = client.post("/api/kb", files=[("files", ("x.exe", b"x", "application/octet-stream"))])
    assert bad.status_code == 422
    assert sorted(p.name for p in kb_dir.iterdir()) == ["evil.md"]


def test_mount_frontend(tmp_path):
    from fastapi import FastAPI

    assert api.mount_frontend(FastAPI(), tmp_path) is False
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    assert api.mount_frontend(FastAPI(), tmp_path) is True
