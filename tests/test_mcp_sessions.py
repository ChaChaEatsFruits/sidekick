import asyncio

import sidekick_tools
from sidekick_tools import McpSessions


def test_cancelling_start_stops_the_servers(monkeypatch):
    """A reset while the browser is still starting must not leave the MCP servers (and browser) running."""

    async def never_ready(self):
        await asyncio.Event().wait()  # stands in for servers that are still starting

    monkeypatch.setattr(McpSessions, "_run", never_ready)

    async def reset_mid_start():
        sessions = McpSessions({})
        starting = asyncio.create_task(sessions.start())
        await asyncio.sleep(0)
        starting.cancel()
        await asyncio.gather(starting, return_exceptions=True)
        return sessions

    assert asyncio.run(reset_mid_start())._stop.is_set()


def test_search_tool_never_holds_a_real_key():
    # the wrapper reads SERPER_API_KEY once, at import, after load_dotenv(override=True)
    assert sidekick_tools.search.api_wrapper.serper_api_key == "placeholder-not-a-real-key"
