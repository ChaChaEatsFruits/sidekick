import os

# Must run before sidekick/sidekick_tools are imported: the Serper wrapper needs a key at import time.
# The tests never call OpenAI, Serper or Pushover, so placeholders are enough.
PLACEHOLDERS = {"OPENAI_API_KEY": "placeholder-not-a-real-key", "SERPER_API_KEY": "placeholder-not-a-real-key"}
os.environ.update(PLACEHOLDERS)

import pytest  # noqa: E402

import sidekick  # noqa: E402,F401  (its load_dotenv(override=True) runs now, so the fixture below wins)
import sidekick_tools  # noqa: E402

# The search tool read SERPER_API_KEY at import, after load_dotenv(override=True) put any real key back.
sidekick_tools.search.api_wrapper.serper_api_key = PLACEHOLDERS["SERPER_API_KEY"]


@pytest.fixture(autouse=True)
def placeholder_keys(monkeypatch):
    """Even when .env holds real keys, tests only ever see placeholders."""
    for name, value in PLACEHOLDERS.items():
        monkeypatch.setenv(name, value)
    for name in ("PUSHOVER_USER", "PUSHOVER_TOKEN"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def kb_dir(monkeypatch, tmp_path):
    """API tests get an empty kb/ of their own, and re-indexing never touches the real Chroma index."""
    import knowledge_base

    monkeypatch.setattr(knowledge_base, "KB_DIR", tmp_path)
    monkeypatch.setattr(knowledge_base, "build_index", lambda *args, **kwargs: len(list(tmp_path.iterdir())))
    return tmp_path


@pytest.fixture
def client(monkeypatch, kb_dir):
    """The real API with FakeSidekick in place of the agent."""
    from fastapi.testclient import TestClient

    import api
    from tests.fake_sidekick import FakeSidekick

    monkeypatch.setattr(api, "Sidekick", FakeSidekick)
    monkeypatch.setattr(FakeSidekick, "setup_delay", 0.0)
    FakeSidekick.instances.clear()
    with TestClient(api.app) as test_client:
        yield test_client
