import pytest

from knowledge_base import build_index, chunk_text, get_chunks, search


@pytest.fixture(scope="module")
def test_index():
    build_index(name="test_index")  # separate collection so tests never touch the real one
    return "test_index"


def test_retrieval_finds_expected_source(test_index):
    hits = search("What is the maximum line length for Python code?", k=5, name=test_index)
    assert hits[0]["source"] == "pep8.md"
    assert hits == sorted(hits, key=lambda h: h["score"], reverse=True)
    real_id = f"{hits[0]['source']}#{hits[0]['chunk']}"
    assert list(get_chunks([real_id, "made_up.md#999"], name=test_index)) == [real_id]


def test_rebuild_after_search_in_same_process(test_index):
    # the Gradio re-index button rebuilds a collection this process has already searched
    first = build_index(name=test_index)
    assert build_index(name=test_index) == first
    assert search("line length", k=1, name=test_index)[0]["source"] == "pep8.md"


def test_format_results_labels_and_filters(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "dummy")  # importing the tools module builds the search wrapper
    from sidekick_tools import format_results
    hits = [
        {"source": "pep8.md", "chunk": 11, "text": "Limit all lines to 79 characters.", "score": 0.57},
        {"source": "pep484.md", "chunk": 3, "text": "unrelated", "score": 0.1},
    ]
    out = format_results(hits)
    assert "[pep8.md#11]" in out and "79 characters" in out
    assert "pep484" not in out
    assert "No sufficient match" in format_results(hits[1:])


def test_chunks_respect_size_and_overlap():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    # overlap: the start of each chunk repeats the end of the one before it
    assert all(b.split()[0] in a for a, b in zip(chunks, chunks[1:]))
    # nothing is lost: every word appears in some chunk
    assert set(text.split()) == set(" ".join(chunks).split())
